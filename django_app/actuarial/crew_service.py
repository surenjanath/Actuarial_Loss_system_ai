"""
CrewAI run orchestration: compact dataset summary, Ollama health check,
workspace-scoped run lock, threaded streaming kickoff → queue events for SSE.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Generator, Iterator

from django.conf import settings

from . import services
from .crew_config import step_tracker_bullets, workflow_lane_for_step_kind
from .workspace_state import WORKSPACE_RUN_SCOPE
from .crew_agents import build_analysis_crew_from_pipeline, chunk_to_event
from .crew_persistence import (
    create_crew_run_placeholder,
    last_event_seq_for_run,
    persist_crew_run_outcome,
    persist_report_draft_event,
    save_report_version_snapshot,
)

# Steps whose streamed output is the single “board report” draft (live panel + persistence).
BOARD_REPORT_STEP_KINDS = frozenset(
    {'initial_report', 'executive', 'revision', 'final_report'}
)
REPORT_DRAFT_THROTTLE_SEC = 0.42
REPORT_DRAFT_CHAR_LEAP = 6000

logger = logging.getLogger(__name__)


def _iso_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def with_ts(ev: dict[str, Any]) -> dict[str, Any]:
    """Attach server UTC timestamp to every SSE payload."""
    out = dict(ev)
    out['ts'] = _iso_ts()
    return out


def _agent_meta_for_index(
    idx: int,
    agents_meta: list[dict[str, Any]],
    pipeline_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    for a in agents_meta:
        if a['task_index'] == idx:
            return dict(a)
    sk = 'generic'
    if pipeline_rows is not None and 0 <= idx < len(pipeline_rows):
        sk = _step_kind_at(pipeline_rows, idx) or 'generic'
    lid, ltitle = workflow_lane_for_step_kind(sk)
    return {
        'id': f'crew-task-{idx}',
        'task_index': idx,
        'role': '',
        'label': f'Task {idx}',
        'step_kind': sk,
        'workflow_lane': lid,
        'workflow_lane_title': ltitle,
        'tracker_bullets': step_tracker_bullets(sk),
    }


def _infer_task_index_from_role_text(
    text: str, agents_meta: list[dict[str, Any]]
) -> int | None:
    """
    Map streamed agent role / task name to our sequential task index.
    CrewAI often leaves chunk.task_index at 0 for every token; role strings are reliable.
    """
    if not text:
        return None
    text_l = text.lower()
    best_idx: int | None = None
    best_len = -1
    for spec in agents_meta:
        r = spec['role'].lower()
        if r in text_l and len(r) > best_len:
            best_len = len(r)
            best_idx = int(spec['task_index'])
    if best_idx is not None:
        return best_idx
    n = len(agents_meta)
    partial = [
        (8, ('final audit report', 'audited report', 'audit report author')),
        (7, ('senior analyst coach', 'analyst coach')),
        (6, ('chief executive officer',)),
        (5, ('revision & correction lead', 'correction lead')),
        (4, ('independent audit lead', 'independent audit', 'audit lead')),
        (3, ('actuarial practice manager', 'practice manager', 'actuarial practice')),
        (2, ('executive reporting lead', 'executive reporting')),
        (1, ('portfolio risk & trend analyst', 'portfolio risk', 'trend analyst')),
        (0, ('reserving & loss development analyst', 'loss development', 'reserving')),
    ]
    for idx, keys in partial:
        if idx >= n:
            continue
        for k in keys:
            if k in text_l:
                return idx
    return None


def _logical_task_index(
    chunk: Any, last: int | None, agents_meta: list[dict[str, Any]]
) -> int:
    """Prefer role-based index; keep previous index when metadata is missing (empty inter-chunk frames)."""
    raw = int(getattr(chunk, 'task_index', 0) or 0)
    role = (getattr(chunk, 'agent_role', None) or '').strip().lower()
    tname = (getattr(chunk, 'task_name', None) or '').strip().lower()
    combined = f'{role} {tname}'.strip()
    if combined:
        inferred = _infer_task_index_from_role_text(combined, agents_meta)
        if inferred is not None:
            return inferred
    if last is not None:
        return last
    n = len(agents_meta)
    if 0 <= raw < n:
        return raw
    return 0

_active_sessions: set[str] = set()
_active_lock = threading.Lock()


def session_key_for_request(request) -> str:
    """Persisted crew runs use a fixed workspace scope (database), not the browser session id."""
    return WORKSPACE_RUN_SCOPE


def acquire_crew_slot(session_key: str) -> bool:
    with _active_lock:
        if session_key in _active_sessions:
            return False
        _active_sessions.add(session_key)
        return True


def release_crew_slot(session_key: str) -> None:
    with _active_lock:
        _active_sessions.discard(session_key)


def ollama_reachable(base_url: str, timeout_sec: float = 2.0) -> bool:
    """GET /api/tags on Ollama; returns True if HTTP 200."""
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def build_dataset_summary(request) -> str:
    """Structured text summary of the session actuarial data (no raw JSON dump)."""
    rng = services.rng_for_request(request)
    rows = services.generate_actuarial_data(rng)
    target_loss_ratio = 0.68
    vuln = services.calculate_vulnerability_probability(
        rows, target_loss_ratio, 0.4, 0.3, 0.3
    )
    metrics = services.dashboard_metrics(rows, vuln, target_loss_ratio)

    lines: list[str] = []
    lines.append('=== Actuarial cohort summary (mock / illustrative session data) ===')
    lines.append(
        f"Years: {rows[0]['accident_year']}–{rows[-1]['accident_year']} (n={metrics['years_analyzed']})"
    )
    lines.append(
        f"Totals — premium {services.format_currency(metrics['total_premium'])}, "
        f"incurred {services.format_currency(metrics['total_incurred'])}, "
        f"claims {metrics['total_claims']:,}"
    )
    lines.append(
        f"Average loss ratio: {services.format_percentage(metrics['avg_loss_ratio'])} "
        f"(target {services.format_percentage(target_loss_ratio)})"
    )
    lines.append(
        f"Loss ratio band: {services.format_percentage(metrics['lr_range_low'])} – "
        f"{services.format_percentage(metrics['lr_range_high'])}"
    )
    lines.append(
        f"Years above target LR: {metrics['years_above_target']}; "
        f"trend mix — up {metrics['trend_up']}, down {metrics['trend_down']}, stable {metrics['trend_stable']}"
    )
    lines.append(
        f"Vulnerability index — avg {metrics['avg_vulnerability']:.1f}, "
        f"range {metrics['min_vulnerability']:.1f}–{metrics['max_vulnerability']:.1f}, "
        f"high-risk years (v>50): {metrics['high_vulnerability_years']}"
    )
    lines.append('Per accident year (key fields):')
    for i, y in enumerate(rows):
        v = vuln[i] if i < len(vuln) else 0.0
        lines.append(
            f"  {y['accident_year']}: LR {services.format_percentage(y['loss_ratio'])}, "
            f"trend {y['trend']}, risk_score {y['risk_score']}, "
            f"reserve_adequacy {y['reserve_adequacy']:.2f}, dev_factor {y['development_factor']:.3f}, "
            f"vulnerability {v:.1f}"
        )
    lines.append('=== End summary ===')
    return '\n'.join(lines)


def _final_report_text_for_pipeline(
    pipeline_rows: list[dict[str, Any]],
    task_buffers: dict[int, str],
    fallback: str,
) -> str:
    fr_idx: int | None = None
    for i, row in enumerate(pipeline_rows):
        if str(row.get('step_kind') or '').lower() == 'final_report':
            fr_idx = i
            break
    if fr_idx is not None and fr_idx in task_buffers:
        t = (task_buffers[fr_idx] or '').strip()
        if t:
            return t
    return (fallback or '').strip()


def _step_kind_at(pipeline_rows: list[dict[str, Any]], idx: int) -> str:
    if 0 <= idx < len(pipeline_rows):
        return str(pipeline_rows[idx].get('step_kind') or '').lower()
    return ''


def _crew_worker(
    dataset_summary: str,
    event_q: queue.Queue,
    session_key: str,
    deadline: float,
    ollama_base_url: str,
    ollama_model: str,
    pipeline_rows: list[dict[str, Any]],
    agents_meta: list[dict[str, Any]],
    crew_run_id: str | None = None,
    company_profile_text: str = '',
) -> None:
    timed_out = False
    task_buffers: dict[int, str] = {}
    success = False
    outer_err = ''
    raw_chain_summary = ''
    sk = session_key[:12] + '…' if len(session_key) > 12 else session_key
    seq_holder: list[int] | None = (
        [last_event_seq_for_run(crew_run_id)] if crew_run_id else None
    )
    last_throttled_emit = 0.0
    last_throttled_len = 0

    def board_finish(task_idx: int) -> None:
        skind = _step_kind_at(pipeline_rows, task_idx)
        if skind not in BOARD_REPORT_STEP_KINDS:
            return
        text = (task_buffers.get(task_idx) or '')[:500000]
        meta = _agent_meta_for_index(task_idx, agents_meta, pipeline_rows)
        event_q.put(
            {
                'type': 'report_draft',
                'content': text,
                'task_index': task_idx,
                'role': meta['role'],
                'step_kind': skind,
                'label': meta.get('label') or '',
                'phase': 'step_end',
            }
        )
        if crew_run_id and seq_holder is not None:
            persist_report_draft_event(
                crew_run_id=crew_run_id,
                seq_holder=seq_holder,
                content=text,
                task_index=task_idx,
                role=meta['role'],
                step_kind=skind,
                label=str(meta.get('label') or ''),
            )
            save_report_version_snapshot(
                crew_run_id=crew_run_id,
                step_index=task_idx,
                step_kind=skind,
                role=meta['role'],
                report_body=text,
                source_raw='',
            )

    def maybe_throttle_board_draft(task_idx: int) -> None:
        nonlocal last_throttled_emit, last_throttled_len
        skind = _step_kind_at(pipeline_rows, task_idx)
        if skind not in BOARD_REPORT_STEP_KINDS:
            return
        text = (task_buffers.get(task_idx) or '')[:500000]
        if not text:
            return
        now = time.time()
        ln = len(text)
        if (now - last_throttled_emit < REPORT_DRAFT_THROTTLE_SEC) and (
            ln - last_throttled_len < REPORT_DRAFT_CHAR_LEAP
        ):
            return
        meta = _agent_meta_for_index(task_idx, agents_meta, pipeline_rows)
        event_q.put(
            {
                'type': 'report_draft',
                'content': text,
                'task_index': task_idx,
                'role': meta['role'],
                'step_kind': skind,
                'label': meta.get('label') or '',
                'phase': 'streaming',
            }
        )
        if crew_run_id and seq_holder is not None:
            persist_report_draft_event(
                crew_run_id=crew_run_id,
                seq_holder=seq_holder,
                content=text,
                task_index=task_idx,
                role=meta['role'],
                step_kind=skind,
                label=str(meta.get('label') or ''),
            )
        last_throttled_emit = now
        last_throttled_len = ln

    try:
        crew = build_analysis_crew_from_pipeline(
            ollama_base_url,
            ollama_model,
            pipeline_rows,
            task_dataset_text=dataset_summary,
            task_company_text=company_profile_text,
        )
        agents_payload = [dict(a) for a in agents_meta]
        event_q.put(
            {
                'type': 'run_start',
                'model': ollama_model,
                'agents': agents_payload,
                'step_manifest': agents_payload,
                'run_id': crew_run_id,
            }
        )
        logger.info('Crew run_start session=%s model=%s agents=%s', sk, ollama_model, len(agents_meta))
        streaming = crew.kickoff(inputs={'dataset_summary': dataset_summary})
        last_task_index: int | None = None
        chunk_count = 0
        tasks_seen: set[int] = set()
        for chunk in streaming:
            if time.time() > deadline:
                timed_out = True
                event_q.put(
                    {
                        'type': 'error',
                        'message': 'Run exceeded configured timeout.',
                    }
                )
                logger.warning('Crew timeout session=%s', sk)
                break
            try:
                idx = _logical_task_index(chunk, last_task_index, agents_meta)
                if last_task_index is not None and idx != last_task_index:
                    board_finish(last_task_index)
                    meta = _agent_meta_for_index(last_task_index, agents_meta, pipeline_rows)
                    event_q.put(
                        {
                            'type': 'task_transition',
                            'phase': 'end',
                            'task_index': last_task_index,
                            'label': meta['label'],
                            'role': meta['role'],
                            'id': meta['id'],
                            'step_kind': meta.get('step_kind')
                            or _step_kind_at(pipeline_rows, last_task_index),
                            'workflow_lane': meta.get('workflow_lane'),
                            'workflow_lane_title': meta.get('workflow_lane_title'),
                            'tracker_bullets': meta.get('tracker_bullets'),
                        }
                    )
                    if settings.CREW_VERBOSE_LOG:
                        logger.debug(
                            'Crew task end session=%s task_index=%s', sk, last_task_index
                        )
                if last_task_index is None or idx != last_task_index:
                    meta = _agent_meta_for_index(idx, agents_meta, pipeline_rows)
                    event_q.put(
                        {
                            'type': 'task_transition',
                            'phase': 'start',
                            'task_index': idx,
                            'label': meta['label'],
                            'role': meta['role'],
                            'id': meta['id'],
                            'step_kind': meta.get('step_kind')
                            or _step_kind_at(pipeline_rows, idx),
                            'workflow_lane': meta.get('workflow_lane'),
                            'workflow_lane_title': meta.get('workflow_lane_title'),
                            'tracker_bullets': meta.get('tracker_bullets'),
                        }
                    )
                    last_task_index = idx
                    if _step_kind_at(pipeline_rows, idx) in BOARD_REPORT_STEP_KINDS:
                        last_throttled_emit = 0.0
                        last_throttled_len = 0
                    if settings.CREW_VERBOSE_LOG:
                        logger.debug(
                            'Crew task start session=%s task_index=%s', sk, idx
                        )
                if idx not in tasks_seen:
                    tasks_seen.add(idx)
                    logger.info(
                        'Crew first chunk task_index=%s agent_role=%s session=%s',
                        idx,
                        getattr(chunk, 'agent_role', '') or '',
                        sk,
                    )
                ev = chunk_to_event(chunk)
                ev['task_index'] = idx
                bit = ev.get('content') or ''
                if bit:
                    task_buffers[idx] = task_buffers.get(idx, '') + bit
                event_q.put(ev)
                if bit:
                    maybe_throttle_board_draft(idx)
                chunk_count += 1
                if settings.CREW_VERBOSE_LOG and chunk_count % 50 == 0:
                    logger.debug('Crew chunks session=%s count=%s', sk, chunk_count)
            except Exception as e:  # noqa: BLE001 — stream chunk serialization
                event_q.put({'type': 'error', 'message': f'Chunk serialize: {e}'})
                logger.exception('Crew chunk serialize session=%s', sk)
        if last_task_index is not None and not timed_out:
            board_finish(last_task_index)
            meta = _agent_meta_for_index(last_task_index, agents_meta, pipeline_rows)
            event_q.put(
                {
                    'type': 'task_transition',
                    'phase': 'end',
                    'task_index': last_task_index,
                    'label': meta['label'],
                    'role': meta['role'],
                    'id': meta['id'],
                    'step_kind': meta.get('step_kind')
                    or _step_kind_at(pipeline_rows, last_task_index),
                    'workflow_lane': meta.get('workflow_lane'),
                    'workflow_lane_title': meta.get('workflow_lane_title'),
                    'tracker_bullets': meta.get('tracker_bullets'),
                }
            )
        if not timed_out:
            try:
                result = streaming.result
                raw = getattr(result, 'raw', None)
                if raw is None:
                    raw = str(result)
                raw_chain_summary = str(raw)
                fr_text = _final_report_text_for_pipeline(
                    pipeline_rows, task_buffers, raw_chain_summary
                )
                event_q.put(
                    {
                        'type': 'result',
                        'summary': raw_chain_summary,
                        'final_report': fr_text,
                        'run_id': crew_run_id,
                        'pending_approval': bool(crew_run_id),
                    }
                )
                success = True
                logger.info(
                    'Crew completed session=%s chunks=%s', sk, chunk_count
                )
            except Exception as e:  # noqa: BLE001
                outer_err = f'Final result: {e}'
                event_q.put({'type': 'error', 'message': outer_err})
                logger.exception('Crew final result session=%s', sk)
    except Exception as e:  # noqa: BLE001 — crew / LLM errors
        outer_err = str(e)
        event_q.put({'type': 'error', 'message': outer_err})
        logger.exception('Crew worker session=%s', sk)
    finally:
        if crew_run_id:
            err_final = ''
            if timed_out:
                err_final = 'Run exceeded configured timeout.'
            elif outer_err:
                err_final = outer_err
            persist_crew_run_outcome(
                crew_run_id=crew_run_id,
                task_buffers=task_buffers,
                pipeline=pipeline_rows,
                success=success and not timed_out,
                error_message=err_final,
                raw_chain_summary=raw_chain_summary,
                default_ollama_model=ollama_model,
            )
        event_q.put(None)
        release_crew_slot(session_key)


def iter_crew_events(
    dataset_summary: str,
    session_key: str,
    ollama_base_url: str,
    ollama_model: str,
    timeout_sec: int,
    pipeline_rows: list[dict[str, Any]],
    agents_meta: list[dict[str, Any]],
    persist_context: dict[str, Any] | None = None,
    company_profile_text: str = '',
) -> Iterator[dict[str, Any]]:
    """
    Yields event dicts for SSE (caller JSON-encodes).
    Ends after sentinel from worker; slot released in worker finally.
    """
    if not settings.CREW_ANALYSIS_ENABLED:
        yield with_ts(
            {
                'type': 'error',
                'message': 'Crew analysis is disabled (CREW_ANALYSIS_ENABLED).',
            }
        )
        return

    if not acquire_crew_slot(session_key):
        yield with_ts(
            {
                'type': 'error',
                'message': 'An analysis is already running for this session. Wait for it to finish.',
            }
        )
        return

    if not ollama_reachable(ollama_base_url):
        release_crew_slot(session_key)
        yield with_ts(
            {
                'type': 'error',
                'message': 'Ollama is not reachable at the configured base URL. Start `ollama serve` or update Settings → Local LLM.',
            }
        )
        return

    crew_run_id: str | None = None
    if persist_context:
        try:
            run = create_crew_run_placeholder(**persist_context)
            crew_run_id = str(run.pk)
        except Exception as e:  # noqa: BLE001
            release_crew_slot(session_key)
            yield with_ts({'type': 'error', 'message': f'Could not start run record: {e}'})
            return

    event_q: queue.Queue = queue.Queue(maxsize=500)
    deadline = time.time() + float(timeout_sec)
    thread = threading.Thread(
        target=_crew_worker,
        args=(
            dataset_summary,
            event_q,
            session_key,
            deadline,
            ollama_base_url,
            ollama_model,
            pipeline_rows,
            agents_meta,
            crew_run_id,
            company_profile_text,
        ),
        daemon=True,
        name='crewai-sse-worker',
    )
    thread.start()
    while True:
        item = event_q.get()
        if item is None:
            break
        yield with_ts(item)


def sse_lines_for_crew(
    dataset_summary: str,
    session_key: str,
    ollama_base_url: str,
    ollama_model: str,
    timeout_sec: int,
    pipeline_rows: list[dict[str, Any]],
    agents_meta: list[dict[str, Any]],
    persist_context: dict[str, Any] | None = None,
    company_profile_text: str = '',
) -> Generator[str, None, None]:
    """Yield SSE-formatted lines for StreamingHttpResponse."""
    for ev in iter_crew_events(
        dataset_summary,
        session_key,
        ollama_base_url,
        ollama_model,
        timeout_sec,
        pipeline_rows,
        agents_meta,
        persist_context,
        company_profile_text=company_profile_text,
    ):
        yield 'data: ' + json.dumps(ev, ensure_ascii=False) + '\n\n'
