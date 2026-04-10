"""
Persist CrewAI runs, per-step transcripts, and cross-run coaching retrieval.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db import close_old_connections
from django.db.models import Max
from django.utils import timezone

from .models import CrewReportVersion, CrewRun, CrewRunEvent, CrewStepOutput

logger = logging.getLogger(__name__)

PRIOR_COACHING_MAX_CHARS = 8000
MAX_LIVE_REPORT_CHARS = 500_000
MAX_EVENT_PAYLOAD_JSON = 600_000


def fetch_prior_coaching_text(session_key: str, member_id: str | None) -> str:
    """
    Latest non-failed run for this session (and optional member) with a coach step;
    returns coach transcript text for injection into the next kickoff.
    """
    close_old_connections()
    try:
        qs = (
            CrewRun.objects.filter(session_key=session_key)
            .exclude(status=CrewRun.Status.FAILED)
            .exclude(status=CrewRun.Status.RUNNING)
            .order_by('-created_at')
        )
        if member_id:
            qs = qs.filter(member_id=member_id)
        else:
            qs = qs.filter(member_id__isnull=True)

        for run in qs[:8]:
            step = run.steps.filter(step_kind='coach').order_by('step_index').first()
            if step and (step.content or '').strip():
                text = step.content.strip()
                if len(text) > PRIOR_COACHING_MAX_CHARS:
                    text = text[:PRIOR_COACHING_MAX_CHARS] + '\n… [truncated]'
                return text
        return ''
    finally:
        close_old_connections()


def create_crew_run_placeholder(
    *,
    session_key: str,
    topic: str,
    member_id: str | None,
    pipeline: list[dict[str, Any]],
    global_instructions: str,
    dataset_summary_snapshot: str = '',
    ollama_base_url: str,
    ollama_model: str,
    timeout_sec: int,
) -> CrewRun:
    return CrewRun.objects.create(
        session_key=session_key[:64],
        member_id=(member_id[:32] if member_id else None),
        topic=(topic or '')[:8000],
        status=CrewRun.Status.RUNNING,
        pipeline_snapshot=list(pipeline),
        dataset_summary_snapshot=(dataset_summary_snapshot or '')[:500000],
        global_instructions_snapshot=(global_instructions or '')[:4000],
        ollama_base_url=(ollama_base_url or '')[:512],
        ollama_model=(ollama_model or '')[:200],
        timeout_sec=max(1, int(timeout_sec)),
    )


def last_event_seq_for_run(crew_run_id: str) -> int:
    """Highest seq stored for this run (0 if none)."""
    close_old_connections()
    try:
        agg = CrewRunEvent.objects.filter(run_id=crew_run_id).aggregate(Max('seq'))
        return int(agg['seq__max'] or 0)
    finally:
        close_old_connections()


def append_crew_run_event(
    crew_run_id: str,
    seq: int,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Append one event row (call from worker thread; uses close_old_connections)."""
    close_old_connections()
    try:
        CrewRunEvent.objects.create(
            run_id=crew_run_id,
            seq=seq,
            event_type=event_type[:32],
            payload=_trim_payload(payload),
        )
    except Exception:
        logger.exception('append_crew_run_event failed run=%s seq=%s', crew_run_id, seq)
    finally:
        close_old_connections()


def _trim_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep payload JSON-serializable and bounded (truncate huge content)."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k == 'content' and isinstance(v, str) and len(v) > MAX_EVENT_PAYLOAD_JSON:
            out[k] = v[:MAX_EVENT_PAYLOAD_JSON] + '\n… [truncated]'
        else:
            out[k] = v
    return out


def update_live_report_snapshot(crew_run_id: str, text: str) -> None:
    """Denormalized board text for polling."""
    close_old_connections()
    try:
        CrewRun.objects.filter(pk=crew_run_id).update(
            live_report_text=(text or '')[:MAX_LIVE_REPORT_CHARS],
            live_report_at=timezone.now(),
        )
    except Exception:
        logger.exception('update_live_report_snapshot failed run=%s', crew_run_id)
    finally:
        close_old_connections()


def save_report_version_snapshot(
    *,
    crew_run_id: str,
    step_index: int,
    step_kind: str,
    role: str,
    report_body: str,
    source_raw: str = '',
) -> None:
    """Point-in-time report body when a board step finishes."""
    close_old_connections()
    try:
        CrewReportVersion.objects.create(
            run_id=crew_run_id,
            step_index=step_index,
            step_kind=(step_kind or '')[:32],
            role=(role or '')[:200],
            report_body=(report_body or '')[:MAX_LIVE_REPORT_CHARS],
            source_raw=(source_raw or '')[:MAX_LIVE_REPORT_CHARS],
        )
    except Exception:
        logger.exception(
            'save_report_version_snapshot failed run=%s step=%s', crew_run_id, step_index
        )
    finally:
        close_old_connections()


def persist_report_draft_event(
    *,
    crew_run_id: str,
    seq_holder: list[int],
    content: str,
    task_index: int,
    role: str,
    step_kind: str,
    label: str = '',
) -> None:
    """
    Emit DB event + live_report update for one report_draft tick.
    seq_holder[0] is incremented; caller initializes to last_event_seq_for_run.
    """
    seq_holder[0] += 1
    seq = seq_holder[0]
    text = (content or '')[:MAX_LIVE_REPORT_CHARS]
    append_crew_run_event(
        crew_run_id,
        seq,
        'report_draft',
        {
            'content': text,
            'task_index': task_index,
            'role': role,
            'step_kind': step_kind,
            'label': label,
        },
    )
    update_live_report_snapshot(crew_run_id, text)


def _final_report_index(pipeline: list[dict[str, Any]]) -> int | None:
    for i, row in enumerate(pipeline):
        if str(row.get('step_kind') or '').lower() == 'final_report':
            return i
    return None


def persist_crew_run_outcome(
    *,
    crew_run_id: str,
    task_buffers: dict[int, str],
    pipeline: list[dict[str, Any]],
    success: bool,
    error_message: str = '',
    raw_chain_summary: str = '',
    default_ollama_model: str = '',
) -> None:
    """Write step rows and final status. Call from worker thread with close_old_connections."""
    close_old_connections()
    try:
        try:
            run = CrewRun.objects.get(pk=crew_run_id)
        except CrewRun.DoesNotExist:
            logger.warning('persist_crew_run_outcome: missing run %s', crew_run_id)
            return

        run.finished_at = timezone.now()
        run.chain_summary = (raw_chain_summary or '')[:500000]
        run.error_message = (error_message or '')[:8000]

        fr_idx = _final_report_index(pipeline)
        if fr_idx is not None and fr_idx in task_buffers:
            run.final_report_text = (task_buffers[fr_idx] or '').strip()
        elif success and raw_chain_summary:
            run.final_report_text = (raw_chain_summary or '').strip()

        if success:
            run.status = CrewRun.Status.PENDING_APPROVAL
        else:
            run.status = CrewRun.Status.FAILED

        previews: list[dict[str, Any]] = []
        for i in range(len(pipeline)):
            raw = (task_buffers.get(i) or '').strip()
            previews.append(
                {
                    'step_index': i,
                    'preview': (raw[:400] + '…') if len(raw) > 400 else raw,
                }
            )
        run.report_draft_versions = previews

        ufs: list[str] = [
            'finished_at',
            'chain_summary',
            'error_message',
            'final_report_text',
            'status',
            'report_draft_versions',
        ]
        if success:
            run.live_report_text = (run.final_report_text or '')[:MAX_LIVE_REPORT_CHARS]
            run.live_report_at = timezone.now()
            ufs.extend(['live_report_text', 'live_report_at'])

        run.save(update_fields=ufs)

        run.steps.all().delete()
        bulk: list[CrewStepOutput] = []
        for i, row in enumerate(pipeline):
            om = (row.get('ollama_model') or '').strip() or default_ollama_model
            bulk.append(
                CrewStepOutput(
                    run=run,
                    step_index=i,
                    step_kind=str(row.get('step_kind') or '')[:32],
                    role=str(row.get('role') or '')[:200],
                    content=task_buffers.get(i, '') or '',
                    ollama_model=om[:200],
                    finished_at=run.finished_at,
                )
            )
        if bulk:
            CrewStepOutput.objects.bulk_create(bulk)
    except Exception:
        logger.exception('persist_crew_run_outcome failed run=%s', crew_run_id)
    finally:
        close_old_connections()
