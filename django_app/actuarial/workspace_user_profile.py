"""
Shared workspace user display (Settings → General): persisted on WorkspaceState singleton.
Defaults align with the first mock team member in services.get_team_members().
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from django.apps import apps

from .crew_config import MAX_AVATAR
from . import services

MAX_DISPLAY_NAME = 200
MAX_EMAIL = 120
MAX_ROLE = 200
MAX_DEPT = 120

_DICEBEAR_INITIALS = 'https://api.dicebear.com/7.x/initials/svg'


def _default_lead() -> dict[str, str]:
    lead = services.get_team_members()[0]
    return {
        'display_name': str(lead.get('name') or '').strip()[:MAX_DISPLAY_NAME],
        'email': str(lead.get('email', '') or '').strip()[:MAX_EMAIL],
        'role': str(lead.get('role') or '').strip()[:MAX_ROLE],
        'department': str(lead.get('department') or '').strip()[:MAX_DEPT],
        'avatar_initials': _sanitize_initials(lead.get('avatar')),
    }


def _sanitize_initials(raw: str | None) -> str:
    if not raw:
        return ''
    s = re.sub(r'[^a-zA-Z0-9]', '', str(raw).strip())[:MAX_AVATAR]
    return s


def _sanitize_display_name(s: str | None) -> str:
    return (str(s or '').strip())[:MAX_DISPLAY_NAME]


def _sanitize_email(s: str | None) -> str:
    return (str(s or '').strip())[:MAX_EMAIL]


def _sanitize_role(s: str | None) -> str:
    return (str(s or '').strip())[:MAX_ROLE]


def _sanitize_department(s: str | None) -> str:
    return (str(s or '').strip())[:MAX_DEPT]


def _row_to_stored(w: Any) -> dict[str, str]:
    return {
        'display_name': _sanitize_display_name(getattr(w, 'workspace_display_name', None)),
        'email': _sanitize_email(getattr(w, 'workspace_email', None)),
        'role': _sanitize_role(getattr(w, 'workspace_role', None)),
        'department': _sanitize_department(getattr(w, 'workspace_department', None)),
        'avatar_initials': _sanitize_initials(getattr(w, 'workspace_avatar_initials', None)),
    }


def _merge_with_defaults(stored: dict[str, str]) -> dict[str, str]:
    d = _default_lead()
    out = dict(d)
    for k in ('display_name', 'email', 'role', 'department', 'avatar_initials'):
        v = stored.get(k) or ''
        if v:
            out[k] = v
    return out


def avatar_url_for_resolved(resolved: dict[str, str]) -> str:
    """Dicebear initials; seed from avatar_initials or display name."""
    initials = (resolved.get('avatar_initials') or '').strip()
    name = (resolved.get('display_name') or '').strip()
    seed = initials if initials else (name or 'User')
    q = urlencode({'seed': seed, 'backgroundColor': '1e293b'})
    return f'{_DICEBEAR_INITIALS}?{q}'


def get_workspace_user_profile() -> dict[str, str]:
    """Raw stored fields from DB (may be empty)."""
    WorkspaceState = apps.get_model('actuarial', 'WorkspaceState')
    w = WorkspaceState.objects.filter(pk=1).first()
    if w is None:
        return {
            'display_name': '',
            'email': '',
            'role': '',
            'department': '',
            'avatar_initials': '',
        }
    return _row_to_stored(w)


def resolve_workspace_user_display() -> dict[str, Any]:
    """Stored values merged with defaults from mock team lead; includes avatar_url."""
    stored = get_workspace_user_profile()
    merged = _merge_with_defaults(stored)
    return {
        **merged,
        'avatar_url': avatar_url_for_resolved(merged),
    }


def set_workspace_user_profile(data: dict[str, Any]) -> tuple[bool, str]:
    """Persist General tab fields; pass empty dict to clear to defaults-only behavior."""
    WorkspaceState = apps.get_model('actuarial', 'WorkspaceState')
    w, _ = WorkspaceState.objects.get_or_create(pk=1)
    prof = {
        'workspace_display_name': _sanitize_display_name(data.get('display_name')),
        'workspace_email': _sanitize_email(data.get('email')),
        'workspace_role': _sanitize_role(data.get('role')),
        'workspace_department': _sanitize_department(data.get('department')),
        'workspace_avatar_initials': _sanitize_initials(data.get('avatar_initials')),
    }
    for k, v in prof.items():
        setattr(w, k, v)
    w.save(
        update_fields=[
            'workspace_display_name',
            'workspace_email',
            'workspace_role',
            'workspace_department',
            'workspace_avatar_initials',
            'updated_at',
        ]
    )
    return True, ''
