"""
Session-stored team member labels and instructions for display + CrewAI context.
"""
from __future__ import annotations

import re
from typing import Any

from . import services
from .company_profile import clear_company_profile
from .persona_defaults import DEFAULT_AI_PERSONA_BY_MEMBER

SESSION_OVERRIDES_KEY = 'team_member_overrides'
SESSION_GLOBAL_INSTRUCTIONS_KEY = 'crew_global_instructions'

MAX_NAME = 80
MAX_ROLE = 100
MAX_DEPT = 80
MAX_AVATAR = 3
MAX_SPEC_LINE = 400
MAX_NOTES = 400
MAX_AI_INSTRUCTIONS = 1200
MAX_GLOBAL_INSTRUCTIONS = 3500


def _trim(s: str | None, max_len: int) -> str:
    if not s:
        return ''
    t = str(s).strip()
    return t[:max_len]


def _parse_specialization(text: str) -> list[str]:
    if not text or not str(text).strip():
        return []
    parts = [p.strip() for p in str(text).split(',')]
    out = [p for p in parts if p][:12]
    return out


def _sanitize_avatar(s: str | None) -> str:
    if not s:
        return ''
    t = re.sub(r'[^a-zA-Z0-9]', '', str(s).strip())[:MAX_AVATAR]
    return t.upper() if t else ''


def get_raw_overrides(request) -> dict[str, dict[str, Any]]:
    from . import workspace_state

    workspace_state.migrate_legacy_session(request)
    w = workspace_state.get_workspace()
    raw = w.member_overrides_json
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    return {}


def get_global_instructions(request) -> str:
    from . import workspace_state

    workspace_state.migrate_legacy_session(request)
    w = workspace_state.get_workspace()
    g = w.global_instructions or ''
    return _trim(g, MAX_GLOBAL_INSTRUCTIONS) if isinstance(g, str) else ''


def set_global_instructions(request, text: str | None) -> None:
    from . import workspace_state

    workspace_state.migrate_legacy_session(request)
    t = _trim(text, MAX_GLOBAL_INSTRUCTIONS)
    w = workspace_state.get_workspace()
    w.global_instructions = t if t else ''
    w.save(update_fields=['global_instructions', 'updated_at'])


def merged_team_members(request) -> list[dict[str, Any]]:
    """Roster with session overrides applied; extra keys personal_notes, has_customization."""
    overrides = get_raw_overrides(request)
    out: list[dict[str, Any]] = []
    for m in services.get_team_members():
        row = dict(m)
        o = overrides.get(m['id'], {})
        if o.get('name'):
            row['name'] = _trim(o.get('name'), MAX_NAME)
        if o.get('role'):
            row['role'] = _trim(o.get('role'), MAX_ROLE)
        if o.get('department'):
            row['department'] = _trim(o.get('department'), MAX_DEPT)
        av = _sanitize_avatar(o.get('avatar'))
        if av:
            row['avatar'] = av
        if o.get('specialization'):
            row['specialization'] = _parse_specialization(str(o.get('specialization', '')))
        notes = _trim(o.get('notes'), MAX_NOTES)
        if 'ai_instructions' in o:
            ai_inst = _trim(o.get('ai_instructions'), MAX_AI_INSTRUCTIONS)
        else:
            ai_inst = _trim(
                DEFAULT_AI_PERSONA_BY_MEMBER.get(m['id'], ''),
                MAX_AI_INSTRUCTIONS,
            )
        row['personal_notes'] = notes
        row['ai_instructions'] = ai_inst
        row['has_customization'] = bool(o)
        out.append(row)
    return out


def patch_member_override(request, member_id: str, data: dict[str, Any]) -> tuple[bool, str]:
    """Apply validated patch; empty strings remove that field from override blob."""
    valid_ids = {m['id'] for m in services.get_team_members()}
    if member_id not in valid_ids:
        return False, 'unknown member id'

    all_o = dict(get_raw_overrides(request))
    cur: dict[str, Any] = dict(all_o.get(member_id, {}))

    for key, max_len in (
        ('name', MAX_NAME),
        ('role', MAX_ROLE),
        ('department', MAX_DEPT),
        ('notes', MAX_NOTES),
        ('ai_instructions', MAX_AI_INSTRUCTIONS),
    ):
        if key not in data:
            continue
        val = data[key]
        if val is None or val == '':
            cur.pop(key, None)
        else:
            cur[key] = _trim(val, max_len)

    if 'avatar' in data:
        av = data['avatar']
        if av is None or av == '':
            cur.pop('avatar', None)
        else:
            s = _sanitize_avatar(str(av))
            if s:
                cur['avatar'] = s

    if 'specialization' in data:
        sp = data['specialization']
        if sp is None or (isinstance(sp, str) and not sp.strip()):
            cur.pop('specialization', None)
        else:
            cur['specialization'] = _trim(sp, MAX_SPEC_LINE)

    if cur:
        all_o[member_id] = cur
    else:
        all_o.pop(member_id, None)

    from . import workspace_state

    w = workspace_state.get_workspace()
    w.member_overrides_json = all_o
    w.save(update_fields=['member_overrides_json', 'updated_at'])
    return True, ''


def clear_member_override(request, member_id: str) -> None:
    all_o = dict(get_raw_overrides(request))
    if member_id not in all_o:
        return
    del all_o[member_id]
    from . import workspace_state

    w = workspace_state.get_workspace()
    w.member_overrides_json = all_o
    w.save(update_fields=['member_overrides_json', 'updated_at'])


def clear_all_overrides(request) -> None:
    from . import workspace_state

    workspace_state.migrate_legacy_session(request)
    clear_company_profile(request)
    w = workspace_state.get_workspace()
    w.member_overrides_json = {}
    w.global_instructions = ''
    w.save(update_fields=['member_overrides_json', 'global_instructions', 'updated_at'])
    from .crew_config import reset_pipeline_to_defaults

    reset_pipeline_to_defaults()


def build_team_context_for_crew(request) -> str:
    """Narrative block appended to dataset summary (global instructions + crew order summary)."""
    from .crew_config import display_label, get_pipeline

    g = get_global_instructions(request)
    pipeline = get_pipeline(request)

    lines: list[str] = []
    if g:
        lines.append('=== User instructions for this analysis (saved workspace) ===')
        lines.append(g)
        lines.append('=== End user instructions ===')

    lines.append(
        '=== Crew run order (saved pipeline; each agent already has role/goal/backstory) ==='
    )
    for i, row in enumerate(pipeline):
        lab = display_label(row)
        lines.append(f"{i + 1}. {lab} — {row['role']}")
    lines.append('=== End crew order ===')
    return '\n'.join(lines)
