"""
SSE stream and health check for CrewAI + Ollama (GET-only; EventSource uses session cookie).
REST helpers for persisted runs, approval, and history.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .crew_board_tokens import BoardTokenError, parse_board_token, sign_board_token
from .models import CrewRunEvent

from . import member_personalization
from .company_profile import format_company_profile_for_crew
from .crew_config import get_pipeline, run_agents_meta_for_pipeline
from .crew_persistence import fetch_prior_coaching_text
from .crew_service import (
    build_dataset_summary,
    ollama_reachable,
    session_key_for_request,
    sse_lines_for_crew,
)
from .member_personalization import build_team_context_for_crew
from .models import CrewRun
from .ollama_session import get_runtime_config
from .report_pdf import build_approved_report_pdf_bytes
from .workflow_handoff import summarize_handoff_from_steps


class _ApproveNotPending(Exception):
    """Raised when select_for_update sees a run that is no longer pending."""


def _run_to_dict(run: CrewRun, *, include_steps: bool, short_chain: bool = True) -> dict[str, Any]:
    chain = run.chain_summary or ''
    if short_chain and len(chain) > 2000:
        chain = chain[:2000] + '…'
    ds_snap = run.dataset_summary_snapshot or ''
    if short_chain and len(ds_snap) > 2000:
        ds_snap = ds_snap[:2000] + '…'
    lr = run.live_report_text or ''
    if short_chain and len(lr) > 500:
        lr = lr[:500] + '…'
    out: dict[str, Any] = {
        'id': str(run.id),
        'status': run.status,
        'topic': run.topic,
        'member_id': run.member_id,
        'final_report_text': run.final_report_text,
        'chain_summary': chain,
        'dataset_summary_snapshot': ds_snap,
        'error_message': run.error_message,
        'created_at': run.created_at.isoformat() if run.created_at else '',
        'finished_at': run.finished_at.isoformat() if run.finished_at else '',
        'approved_at': run.approved_at.isoformat() if run.approved_at else '',
        'ollama_model': run.ollama_model,
        'live_report_text': lr,
        'live_report_at': run.live_report_at.isoformat() if run.live_report_at else '',
        'has_approved_pdf': bool(run.approved_report_pdf),
    }
    if include_steps:
        out['steps'] = [
            {
                'step_index': s.step_index,
                'step_kind': s.step_kind,
                'role': s.role,
                'content': s.content,
                'ollama_model': s.ollama_model,
            }
            for s in run.steps.all().order_by('step_index')
        ]
        out['workflow_handoff'] = summarize_handoff_from_steps(out['steps'])
    return out


@login_required
@require_GET
def crew_health(request):
    """JSON: { ok, model, enabled, ollama_url } — for UI before starting EventSource."""
    rt = get_runtime_config(request)
    if not settings.CREW_ANALYSIS_ENABLED:
        return JsonResponse(
            {
                'ok': False,
                'enabled': False,
                'model': rt['model'],
                'ollama_url': rt['base_url'],
                'message': 'Crew analysis is disabled. Set CREW_ANALYSIS_ENABLED=true.',
            }
        )
    reachable = ollama_reachable(rt['base_url'])
    return JsonResponse(
        {
            'ok': reachable,
            'enabled': True,
            'model': rt['model'],
            'ollama_url': rt['base_url'],
            'timeout_sec': rt['timeout_sec'],
            'session_override': rt['from_session'],
            'message': '' if reachable else 'Ollama not reachable at the configured base URL.',
        }
    )


@login_required
@require_GET
def crew_stream(request):
    """
    Server-Sent Events stream of crew run progress and final result.
    Query: topic — prepended as focus line; member_id — optional roster id for learnings + persistence.
    """
    topic = (request.GET.get('topic') or '').strip()
    member_id = (request.GET.get('member_id') or '').strip() or None

    parts = [build_dataset_summary(request)]
    org_block = format_company_profile_for_crew(request).strip()
    if org_block:
        parts.append(org_block)
    team_ctx = build_team_context_for_crew(request).strip()
    if team_ctx:
        parts.append(team_ctx)

    prior = fetch_prior_coaching_text(session_key_for_request(request), member_id)
    if prior:
        parts.append(
            '=== Prior run coaching (carry forward — apply on this run) ===\n'
            + prior
            + '\n=== End prior coaching ==='
        )

    summary = '\n\n'.join(parts)
    if topic:
        summary = f'User focus / topic: {topic}\n\n{summary}'

    session_key = session_key_for_request(request)
    rt = get_runtime_config(request)
    pipeline = get_pipeline(request)
    agents_meta = run_agents_meta_for_pipeline(pipeline)

    company_profile_text = org_block if org_block else ''

    persist_context = {
        'session_key': session_key,
        'topic': topic,
        'member_id': member_id,
        'pipeline': pipeline,
        'global_instructions': member_personalization.get_global_instructions(request),
        'dataset_summary_snapshot': summary,
        'ollama_base_url': rt['base_url'],
        'ollama_model': rt['model'],
        'timeout_sec': int(rt['timeout_sec']),
    }

    response = StreamingHttpResponse(
        sse_lines_for_crew(
            summary,
            session_key,
            rt['base_url'],
            rt['model'],
            int(rt['timeout_sec']),
            pipeline,
            agents_meta,
            persist_context,
            company_profile_text=company_profile_text,
        ),
        content_type='text/event-stream; charset=utf-8',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
@require_GET
def crew_run_latest(request):
    """Latest saved run for this session (optional member_id filter)."""
    sk = session_key_for_request(request)
    member_id = (request.GET.get('member_id') or '').strip() or None
    qs = CrewRun.objects.filter(session_key=sk).order_by('-created_at')
    if member_id:
        qs = qs.filter(member_id=member_id)
    else:
        qs = qs.filter(member_id__isnull=True)
    run = qs.first()
    if not run:
        return JsonResponse({'ok': True, 'run': None})
    return JsonResponse({'ok': True, 'run': _run_to_dict(run, include_steps=True)})


def _run_for_board(request, run_id, token: str | None) -> CrewRun | None:
    """Session ownership or signed token (token must match run_id)."""
    if token:
        try:
            rid = parse_board_token(token)
        except BoardTokenError:
            return None
        if str(rid) != str(run_id):
            return None
        return CrewRun.objects.filter(pk=run_id).first()
    sk = session_key_for_request(request)
    return CrewRun.objects.filter(pk=run_id, session_key=sk).first()


@login_required
@require_GET
def crew_run_detail(request, run_id):
    sk = session_key_for_request(request)
    run = get_object_or_404(CrewRun, pk=run_id, session_key=sk)
    tok = sign_board_token(run.id)
    board_path = reverse('crew_board')
    board_url = request.build_absolute_uri(f'{board_path}?token={tok}')
    return JsonResponse(
        {
            'ok': True,
            'run': _run_to_dict(run, include_steps=True, short_chain=False),
            'board_url': board_url,
            'board_token': tok,
        }
    )


@require_GET
def crew_run_board(request, run_id):
    """Pollable board snapshot: live report text + status (session or ?token=)."""
    token = (request.GET.get('token') or '').strip() or None
    run = _run_for_board(request, run_id, token)
    if not run:
        return JsonResponse({'ok': False, 'error': 'Not found or forbidden.'}, status=404)
    return JsonResponse(
        {
            'ok': True,
            'run_id': str(run.id),
            'status': run.status,
            'live_report_text': run.live_report_text or '',
            'live_report_at': run.live_report_at.isoformat() if run.live_report_at else '',
            'final_report_text': run.final_report_text or '',
            'topic': run.topic or '',
            'error_message': run.error_message or '',
        }
    )


@require_GET
def crew_run_events(request, run_id):
    """Incremental CrewRunEvent rows for replay (session or ?token=)."""
    token = (request.GET.get('token') or '').strip() or None
    run = _run_for_board(request, run_id, token)
    if not run:
        return JsonResponse({'ok': False, 'error': 'Not found or forbidden.'}, status=404)
    after = request.GET.get('after_seq') or '0'
    try:
        after_seq = max(0, int(after))
    except ValueError:
        after_seq = 0
    limit = min(200, int(request.GET.get('limit') or '100'))
    qs = (
        run.run_events.filter(seq__gt=after_seq)
        .order_by('seq')[:limit]
    )
    rows = [
        {'seq': e.seq, 'event_type': e.event_type, 'payload': e.payload, 'created_at': e.created_at.isoformat()}
        for e in qs
    ]
    last_seq = rows[-1]['seq'] if rows else after_seq
    return JsonResponse({'ok': True, 'run_id': str(run.id), 'events': rows, 'last_seq': last_seq})


@require_GET
def crew_board_page(request):
    """Minimal read-only board display; requires ?token= from crew_run_detail."""
    token = (request.GET.get('token') or '').strip()
    if not token:
        return render(
            request,
            'actuarial/crew_board.html',
            {'error': 'Missing token. Open the board link from a crew run detail response.'},
            status=400,
        )
    try:
        rid = parse_board_token(token)
    except BoardTokenError as e:
        return render(
            request,
            'actuarial/crew_board.html',
            {'error': str(e)},
            status=403,
        )
    run = CrewRun.objects.filter(pk=rid).first()
    if not run:
        return render(
            request,
            'actuarial/crew_board.html',
            {'error': 'Run not found.'},
            status=404,
        )
    api_url = reverse('crew_run_board', kwargs={'run_id': run.id})
    return render(
        request,
        'actuarial/crew_board.html',
        {
            'error': None,
            'run_id': str(run.id),
            'token': token,
            'poll_url': request.build_absolute_uri(f'{api_url}?token={token}'),
        },
    )


@login_required
@require_POST
def crew_run_approve(request, run_id):
    sk = session_key_for_request(request)
    run = get_object_or_404(CrewRun, pk=run_id, session_key=sk)
    if run.status != CrewRun.Status.PENDING_APPROVAL:
        return JsonResponse(
            {
                'ok': False,
                'error': 'Run is not waiting for approval.',
                'status': run.status,
            },
            status=400,
        )

    try:
        with transaction.atomic():
            locked = CrewRun.objects.select_for_update().get(pk=run_id, session_key=sk)
            if locked.status != CrewRun.Status.PENDING_APPROVAL:
                raise _ApproveNotPending
            locked.status = CrewRun.Status.APPROVED
            locked.approved_at = timezone.now()
            locked.save(update_fields=['status', 'approved_at'])
            pdf_bytes = build_approved_report_pdf_bytes(locked)
            fname = f'report_{locked.id}.pdf'
            locked.approved_report_pdf.save(fname, ContentFile(pdf_bytes), save=True)
            run = locked
    except _ApproveNotPending:
        return JsonResponse(
            {
                'ok': False,
                'error': 'Run is not waiting for approval.',
            },
            status=400,
        )
    except CrewRun.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Not found.'}, status=404)
    except Exception as exc:
        return JsonResponse(
            {'ok': False, 'error': f'Could not finalize approval (PDF): {exc}'},
            status=500,
        )

    run.refresh_from_db()
    return JsonResponse(
        {
            'ok': True,
            'run': _run_to_dict(run, include_steps=False),
        }
    )


@login_required
@require_GET
def crew_run_list(request):
    """Recent runs for this session (cap 20). Optional ?member_id= matches crew_run_latest."""
    sk = session_key_for_request(request)
    member_id = (request.GET.get('member_id') or '').strip() or None
    qs = CrewRun.objects.filter(session_key=sk).order_by('-created_at')
    if member_id:
        qs = qs.filter(member_id=member_id)
    else:
        qs = qs.filter(member_id__isnull=True)
    rows = qs[:20]
    return JsonResponse(
        {
            'ok': True,
            'runs': [_run_to_dict(r, include_steps=False) for r in rows],
        }
    )


@login_required
@require_POST
def crew_run_delete(request, run_id):
    """Remove a run and related rows (CASCADE); delete stored PDF file if present."""
    sk = session_key_for_request(request)
    run = get_object_or_404(CrewRun, pk=run_id, session_key=sk)
    rid = str(run.id)
    if run.approved_report_pdf:
        run.approved_report_pdf.delete(save=False)
    run.delete()
    return JsonResponse({'ok': True, 'id': rid})


@login_required
@require_GET
def crew_run_pdf(request, run_id):
    """Download stored PDF for an approved run (same session as run owner)."""
    sk = session_key_for_request(request)
    run = get_object_or_404(CrewRun, pk=run_id, session_key=sk)
    if run.status != CrewRun.Status.APPROVED or not run.approved_report_pdf:
        return JsonResponse(
            {'ok': False, 'error': 'No approved PDF for this run.'},
            status=404,
        )
    try:
        fh = run.approved_report_pdf.open('rb')
    except FileNotFoundError:
        return JsonResponse(
            {'ok': False, 'error': 'PDF file missing on disk.'},
            status=404,
        )
    resp = FileResponse(fh, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="crew-report-{run.id}.pdf"'
    return resp
