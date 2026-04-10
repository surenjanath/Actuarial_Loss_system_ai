"""Template context processors."""
from __future__ import annotations

from .workspace_user_profile import resolve_workspace_user_display


def workspace_user(request):
    return {'workspace_user': resolve_workspace_user_display()}
