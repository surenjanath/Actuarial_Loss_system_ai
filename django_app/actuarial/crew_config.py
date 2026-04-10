"""
Session-stored Crew agent pipeline: role, goal, backstory, step_kind, optional per-agent Ollama model.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

SESSION_PIPELINE_KEY = 'crew_agent_pipeline'  # legacy session key; migrated by workspace_state.migrate_legacy_session

MIN_PIPELINE_LEN = 2
MAX_PIPELINE_LEN = 16

MAX_ROLE = 200
MAX_GOAL = 1200
MAX_BACKSTORY = 4000
MAX_MODEL = 120
MAX_LABEL = 80
MAX_DEPT = 80
MAX_AVATAR = 3

# step_kind -> UI label + default short label for pipeline cards
STEP_KIND_CHOICES: list[tuple[str, str, str]] = [
    ('reserving', 'Reserving', 'Loss development review'),
    ('risk', 'Risk & trends', 'Portfolio risk'),
    ('initial_report', 'Initial report draft', 'First v1 leadership draft'),
    ('executive', 'Executive brief', 'Synthesis'),
    ('manager', 'Manager review', 'Practice review'),
    ('audit', 'Audit', 'Source check'),
    ('revision', 'Revision', 'Correct & merge'),
    ('ceo', 'CEO sign-off', 'Human handoff'),
    ('coach', 'Analyst feedback', 'Next-run coaching'),
    ('final_report', 'Audited report', 'Leadership deliverable'),
    ('generic', 'Custom step', 'General analysis'),
]

STEP_KINDS_ALLOWED = frozenset(k for k, _, _ in STEP_KIND_CHOICES)

# Analyst-only streamed findings (side pane); must match crew_stream.js if hardcoded there.
ANALYST_STEP_KINDS = frozenset({'reserving', 'risk'})

# Org-style lane order (tier) for UI grouping.
WORKFLOW_LANE_ORDER: tuple[str, ...] = (
    'findings',
    'board',
    'review',
    'approval',
    'finalize',
)

# step_kind -> (lane_id, lane_title)
WORKFLOW_LANE_BY_KIND: dict[str, tuple[str, str]] = {
    'reserving': ('findings', 'Findings'),
    'risk': ('findings', 'Findings'),
    'initial_report': ('board', 'Board draft'),
    'executive': ('board', 'Board draft'),
    'manager': ('review', 'Peer review'),
    'audit': ('review', 'Peer review'),
    'revision': ('approval', 'Sign-off and corrections'),
    'ceo': ('approval', 'Sign-off and corrections'),
    'final_report': ('finalize', 'Deliverable'),
    'coach': ('finalize', 'Deliverable'),
    'generic': ('findings', 'Findings'),
}


def workflow_lane_for_step_kind(kind: str) -> tuple[str, str]:
    """Return (lane_id, lane_title) for org-chart tier grouping."""
    k = (kind or 'generic').strip().lower() or 'generic'
    return WORKFLOW_LANE_BY_KIND.get(k, ('findings', 'Findings'))


def step_tracker_bullets(kind: str) -> list[str]:
    """Static role expectations per step (UI checklist; not LLM-judged)."""
    k = (kind or 'generic').strip().lower() or 'generic'
    table: dict[str, list[str]] = {
        'reserving': [
            'Ground every number in the cohort summary; no invented years or metrics.',
            'Call out IBNR / development patterns and reserve adequacy signals explicitly.',
            'Stay concise; numbered findings preferred.',
        ],
        'risk': [
            'Tie trends and drivers to the summary data; avoid speculative figures.',
            'Flag concentration, deterioration, or volatility with conservative wording.',
            'Separate facts from interpretation.',
        ],
        'initial_report': [
            'Build the leadership draft only from analyst outputs + cohort summary for numbers.',
            'Use board-paper structure cues (title, exec snapshot, sections).',
            'Do not resolve manager/audit comments yet—later steps will refine.',
        ],
        'executive': [
            'Synthesize for leadership: implications, actions, caveats (mock-data caveat if applicable).',
            'Keep tone decisive and short; no dialogue A/B/C format in the board pack.',
        ],
        'manager': [
            'Review for clarity, gaps, and whether conclusions follow from prior tasks.',
            'Do not recompute reserves; critique structure and reasoning.',
        ],
        'audit': [
            'Cross-check factual and numeric claims against the original cohort summary.',
            'Use Pass / Issue with brief evidence; flag contradictions between tasks.',
        ],
        'revision': [
            'Implement manager and audit feedback on the board narrative.',
            'Fix inconsistencies without inventing numbers beyond cohort + prior tasks.',
        ],
        'ceo': [
            'Give go / no-go style assurance for a non-technical reader.',
            'State what still needs caution; one clear handoff line.',
        ],
        'final_report': [
            'Produce the single audited board paper (formal sections, professional tone).',
            'Merge prior steps including CEO sign-off; no internal coaching structure in output.',
        ],
        'coach': [
            'Internal-only feedback for the next run; not part of the board pack.',
            'Address reserving, risk, and exec personas with concrete next-run tips.',
        ],
        'generic': [
            'Build on prior task outputs and cite the cohort summary.',
            'Stay concise and structured.',
        ],
    }
    return table.get(k, table['generic'])


def step_tracker_map_all() -> dict[str, list[str]]:
    """All step kinds with tracker bullets (for JSON in template)."""
    return {k: step_tracker_bullets(k) for k in STEP_KINDS_ALLOWED}


def crew_display_by_lanes(crew_display: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Group pipeline rows by workflow lane for org-style UI.
    Each group: {lane_id, lane_title, agents: [{...row, task_index}, ...]}.
    """
    buckets: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(crew_display):
        kind = str(row.get('step_kind') or 'generic')
        lid, title = workflow_lane_for_step_kind(kind)
        if lid not in buckets:
            buckets[lid] = {'lane_id': lid, 'lane_title': title, 'agents': []}
        r = dict(row)
        r['task_index'] = i
        buckets[lid]['agents'].append(r)
    return [buckets[lid] for lid in WORKFLOW_LANE_ORDER if lid in buckets]


def step_kind_label(kind: str) -> str:
    for k, lab, _ in STEP_KIND_CHOICES:
        if k == kind:
            return lab
    return 'Task'


def step_kind_subtitle(kind: str) -> str:
    for k, _, sub in STEP_KIND_CHOICES:
        if k == kind:
            return sub
    return ''


def new_agent_id() -> str:
    return f'ca-{uuid.uuid4().hex[:12]}'


def _trim(s: str | None, max_len: int) -> str:
    if s is None:
        return ''
    t = str(s).strip()
    return t[:max_len]


def default_pipeline_copy() -> list[dict[str, Any]]:
    """Fresh copy of built-in defaults (no DB write)."""
    return [dict(r) for r in _default_pipeline_rows()]


def _default_pipeline_rows() -> list[dict[str, Any]]:
    """Eight agents matching legacy crew_agents defaults."""
    rows: list[dict[str, Any]] = [
        {
            'id': 'ca-seed-reserving',
            'step_kind': 'reserving',
            'role': 'Reserving & loss development analyst',
            'goal': 'Extract factual patterns from cohort metrics and flag reserving concerns.',
            'backstory': (
                'You are a senior actuary focused on loss triangles, IBNR, and development. '
                'You write precise, numbered findings grounded only in the data provided.'
            ),
            'ollama_model': '',
            'label': '',
            'avatar': 'R1',
            'department': 'Analytics',
        },
        {
            'id': 'ca-seed-risk',
            'step_kind': 'risk',
            'role': 'Portfolio risk & trend analyst',
            'goal': 'Interpret vulnerability drivers, trends, and concentration risk for the cohort.',
            'backstory': (
                'You specialize in risk scoring, trend direction, and explaining what could drive '
                'deterioration or improvement year over year. You stay conservative and cite the summary.'
            ),
            'ollama_model': '',
            'label': '',
            'avatar': 'R2',
            'department': 'Risk',
        },
        {
            'id': 'ca-seed-initial-report',
            'step_kind': 'initial_report',
            'role': 'Leadership report author (first draft)',
            'goal': (
                'Produce version 1 of the leadership-facing report from the reserving and risk analyses, '
                'using organization branding when provided.'
            ),
            'backstory': (
                'You write clear, board-ready prose. You integrate the two analyst streams into one coherent '
                'narrative draft with title block, executive snapshot, and key bullets—knowing that later steps '
                'will refine and audit your text.'
            ),
            'ollama_model': '',
            'label': '',
            'avatar': 'D1',
            'department': 'Analytics',
        },
        {
            'id': 'ca-seed-exec',
            'step_kind': 'executive',
            'role': 'Executive reporting lead',
            'goal': 'Deliver a concise leadership brief with implications and next steps.',
            'backstory': (
                'You synthesize technical actuarial work into clear briefs for leadership: short paragraphs, '
                'bullet actions, and explicit caveats that the input is modelled mock data.'
            ),
            'ollama_model': '',
            'label': '',
            'avatar': 'E1',
            'department': 'Analytics',
        },
        {
            'id': 'ca-seed-mgr',
            'step_kind': 'manager',
            'role': 'Actuarial practice manager',
            'goal': 'Review the analysis package for leadership readiness, gaps, and coherence.',
            'backstory': (
                'You are a senior manager who reads reserving, risk, and executive outputs together. '
                'You judge clarity, completeness, and whether conclusions follow from prior task outputs. '
                'You do not recompute numbers; you critique structure and reasoning.'
            ),
            'ollama_model': '',
            'label': '',
            'avatar': 'M1',
            'department': 'Analytics',
        },
        {
            'id': 'ca-seed-audit',
            'step_kind': 'audit',
            'role': 'Independent audit lead',
            'goal': 'Check factual consistency of claims against the source cohort summary.',
            'backstory': (
                'You compare every quantitative or factual claim in prior outputs to the original '
                'dataset summary. You flag unsupported figures, contradictions between tasks, or '
                'overconfident language. You use Pass/Issue with brief evidence.'
            ),
            'ollama_model': '',
            'label': '',
            'avatar': 'A1',
            'department': 'Assurance',
        },
        {
            'id': 'ca-seed-revision',
            'step_kind': 'revision',
            'role': 'Revision & correction lead',
            'goal': 'Merge manager and audit findings into one corrected, leadership-ready package.',
            'backstory': (
                'You own the revision pass after peer review and audit. You reconcile Pass/Issue items with '
                'the executive narrative, fix inconsistencies, and tighten wording—without inventing new '
                'numbers beyond what the cohort summary and prior tasks support.'
            ),
            'ollama_model': '',
            'label': '',
            'avatar': 'RV',
            'department': 'Analytics',
        },
        {
            'id': 'ca-seed-ceo',
            'step_kind': 'ceo',
            'role': 'Chief executive officer',
            'goal': 'Give a clear go / no-go style sign-off for the human user who will consume the analysis.',
            'backstory': (
                'You speak as the final executive sponsor. Your priority is plain-language assurance: whether '
                'the human can rely on the package, what still needs caution, and a single obvious handoff line. '
                'You do not re-audit every number; you synthesize risk and approval for a non-technical reader.'
            ),
            'ollama_model': '',
            'label': '',
            'avatar': 'CEO',
            'department': 'Executive',
        },
        {
            'id': 'ca-seed-final-report',
            'step_kind': 'final_report',
            'role': 'Final audit report author',
            'goal': (
                'Produce the single leadership-ready audited BOARD PAPER for human sign-off, using all prior '
                'task outputs up to and including CEO sign-off (coaching runs after you in the pipeline).'
            ),
            'backstory': (
                'You own the final written deliverable before internal coaching. You synthesize reserving, risk, '
                'executive, manager, audit, revision, and CEO sign-off into one coherent board paper. '
                'You do not use A/B/C coaching structure—output is the formal sections 1–10 only. Professional tone.'
            ),
            'ollama_model': '',
            'label': '',
            'avatar': 'AR',
            'department': 'Assurance',
        },
        {
            'id': 'ca-seed-coach',
            'step_kind': 'coach',
            'role': 'Senior analyst coach',
            'goal': 'Give targeted feedback for the next run, after the audited board paper is fixed.',
            'backstory': (
                'You see the full pipeline including the final audited board paper. You coach three personas: '
                'reserving analyst, risk analyst, and executive lead. For each, what worked, what was wrong or '
                'missing, and concrete guidance for the next run. Output is internal-only, not part of the board pack.'
            ),
            'ollama_model': '',
            'label': '',
            'avatar': 'C1',
            'department': 'Analytics',
        },
    ]
    return rows


def _sanitize_avatar(raw: str | None) -> str:
    if not raw:
        return ''
    s = re.sub(r'[^a-zA-Z0-9]', '', str(raw).strip())[:MAX_AVATAR]
    return s.upper()


def normalize_pipeline_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Return cleaned row or None if invalid."""
    rid = _trim(raw.get('id'), 64)
    if not rid:
        return None
    sk = _trim(raw.get('step_kind'), 32).lower() or 'generic'
    if sk not in STEP_KINDS_ALLOWED:
        sk = 'generic'
    role = _trim(raw.get('role'), MAX_ROLE)
    goal = _trim(raw.get('goal'), MAX_GOAL)
    backstory = _trim(raw.get('backstory'), MAX_BACKSTORY)
    if not role or not goal:
        return None
    om = _trim(raw.get('ollama_model'), MAX_MODEL)
    lab = _trim(raw.get('label'), MAX_LABEL)
    dept = _trim(raw.get('department'), MAX_DEPT)
    av = _sanitize_avatar(raw.get('avatar'))
    return {
        'id': rid,
        'step_kind': sk,
        'role': role,
        'goal': goal,
        'backstory': backstory,
        'ollama_model': om,
        'label': lab,
        'avatar': av,
        'department': dept,
    }


def validate_pipeline(rows: list[dict[str, Any]]) -> tuple[bool, str]:
    if not rows:
        return False, 'Pipeline is empty.'
    if len(rows) < MIN_PIPELINE_LEN:
        return False, f'At least {MIN_PIPELINE_LEN} agents are required.'
    if len(rows) > MAX_PIPELINE_LEN:
        return False, f'At most {MAX_PIPELINE_LEN} agents allowed.'
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for raw in rows:
        row = normalize_pipeline_row(raw if isinstance(raw, dict) else {})
        if row is None:
            return False, 'Each agent needs id, role, and goal.'
        if row['id'] in seen:
            return False, 'Duplicate agent id.'
        seen.add(row['id'])
        cleaned.append(row)
    return True, ''


def get_pipeline(request=None) -> list[dict[str, Any]]:
    """Load crew pipeline from WorkspaceState (database). Optional request migrates legacy session once."""
    from . import workspace_state

    if request is not None:
        workspace_state.migrate_legacy_session(request)
    w = workspace_state.get_workspace()
    raw = w.pipeline_json
    if not raw or not isinstance(raw, list):
        rows = _default_pipeline_rows()
        w.pipeline_json = [dict(r) for r in rows]
        w.save(update_fields=['pipeline_json', 'updated_at'])
        return [dict(r) for r in rows]

    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = normalize_pipeline_row(item)
        if row:
            out.append(row)
    if len(out) < MIN_PIPELINE_LEN:
        rows = _default_pipeline_rows()
        w.pipeline_json = [dict(r) for r in rows]
        w.save(update_fields=['pipeline_json', 'updated_at'])
        return [dict(r) for r in rows]
    return out


def set_pipeline(request, rows: list[dict[str, Any]]) -> tuple[bool, str]:
    from . import workspace_state

    workspace_state.migrate_legacy_session(request)
    ok, err = validate_pipeline(rows)
    if not ok:
        return False, err
    cleaned = []
    for raw in rows:
        c = normalize_pipeline_row(raw if isinstance(raw, dict) else {})
        if c:
            cleaned.append(c)

    w = workspace_state.get_workspace()
    w.pipeline_json = cleaned
    w.save(update_fields=['pipeline_json', 'updated_at'])
    return True, ''


def reset_pipeline_to_defaults() -> None:
    """Persist built-in default pipeline to the database."""
    from . import workspace_state

    rows = _default_pipeline_rows()
    w = workspace_state.get_workspace()
    w.pipeline_json = [dict(r) for r in rows]
    w.save(update_fields=['pipeline_json', 'updated_at'])


def display_label(row: dict[str, Any]) -> str:
    lab = (row.get('label') or '').strip()
    if lab:
        return lab
    return step_kind_label(str(row.get('step_kind') or 'generic'))


def run_agents_meta_for_pipeline(pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Metadata for SSE run_start, task_transition, and step_manifest."""
    out: list[dict[str, Any]] = []
    for i, row in enumerate(pipeline):
        sk = str(row.get('step_kind') or 'generic')
        lid, ltitle = workflow_lane_for_step_kind(sk)
        out.append(
            {
                'id': f"crew-task-{i}",
                'task_index': i,
                'role': row['role'],
                'label': display_label(row),
                'step_kind': sk,
                'workflow_lane': lid,
                'workflow_lane_title': ltitle,
                'tracker_bullets': step_tracker_bullets(sk),
            }
        )
    return out


def default_generic_row() -> dict[str, Any]:
    return {
        'id': new_agent_id(),
        'step_kind': 'generic',
        'role': 'Analysis specialist',
        'goal': 'Review prior outputs and add insight grounded in the cohort summary.',
        'backstory': (
            'You are a careful analyst. Build on previous tasks, cite the data, and stay concise.'
        ),
        'ollama_model': '',
        'label': '',
        'avatar': 'G',
        'department': 'Analytics',
    }
