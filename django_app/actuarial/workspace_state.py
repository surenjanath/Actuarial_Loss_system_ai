"""
Singleton workspace persistence (database) — replaces Django session for crew config,
personalization, Ollama overrides, and actuarial mock seed.

Crew runs are scoped with WORKSPACE_RUN_SCOPE (not the browser session id).
"""
from __future__ import annotations

import random
from typing import Any

from django.apps import apps

from .crew_config import SESSION_PIPELINE_KEY, MIN_PIPELINE_LEN, validate_pipeline

WORKSPACE_RUN_SCOPE = 'default'


def get_workspace():
    """Return the singleton WorkspaceState row (pk=1)."""
    WorkspaceState = apps.get_model('actuarial', 'WorkspaceState')
    w, _ = WorkspaceState.objects.get_or_create(pk=1)
    return w


def migrate_legacy_session(request) -> None:
    """
    One-time lift from Django session keys (legacy) into WorkspaceState, then clear those keys.
    Safe to call on every request; no-ops when nothing is in session.
    """
    if not getattr(request, 'session', None):
        return
    WorkspaceState = apps.get_model('actuarial', 'WorkspaceState')
    w = get_workspace()
    changed = False

    from .member_personalization import (
        MAX_GLOBAL_INSTRUCTIONS,
        SESSION_GLOBAL_INSTRUCTIONS_KEY,
        SESSION_OVERRIDES_KEY,
    )
    from .ollama_session import SESSION_BASE_URL, SESSION_MODEL, SESSION_TIMEOUT

    if SESSION_PIPELINE_KEY in request.session:
        raw = request.session.get(SESSION_PIPELINE_KEY)
        if isinstance(raw, list):
            ok, _ = validate_pipeline(raw)
            if ok:
                w.pipeline_json = raw
                changed = True
        request.session.pop(SESSION_PIPELINE_KEY, None)

    if SESSION_OVERRIDES_KEY in request.session:
        raw = request.session.get(SESSION_OVERRIDES_KEY)
        if isinstance(raw, dict):
            w.member_overrides_json = {str(k): v for k, v in raw.items() if isinstance(v, dict)}
            changed = True
        request.session.pop(SESSION_OVERRIDES_KEY, None)

    if SESSION_GLOBAL_INSTRUCTIONS_KEY in request.session:
        g = request.session.get(SESSION_GLOBAL_INSTRUCTIONS_KEY)
        if isinstance(g, str):
            w.global_instructions = g[:MAX_GLOBAL_INSTRUCTIONS]
            changed = True
        request.session.pop(SESSION_GLOBAL_INSTRUCTIONS_KEY, None)

    for sk, attr in (
        (SESSION_BASE_URL, 'ollama_base_url'),
        (SESSION_MODEL, 'ollama_model'),
    ):
        if sk in request.session:
            val = request.session.pop(sk)
            if val is not None:
                setattr(w, attr, str(val).strip()[:512] if attr.endswith('url') else str(val).strip()[:200])
                changed = True

    if SESSION_TIMEOUT in request.session:
        raw = request.session.pop(SESSION_TIMEOUT)
        try:
            if raw is not None and str(raw).strip() != '':
                v = max(60, min(3600, int(raw)))
                w.crew_timeout_sec = v
                changed = True
        except (TypeError, ValueError):
            pass

    if 'actuarial_seed' in request.session:
        try:
            w.actuarial_seed = int(request.session.pop('actuarial_seed'))
            changed = True
        except (TypeError, ValueError):
            request.session.pop('actuarial_seed', None)

    if changed:
        w.save()
    request.session.modified = True


def ensure_actuarial_seed_in_db() -> int:
    """Stable mock dataset seed in the database."""
    w = get_workspace()
    if w.actuarial_seed is None:
        w.actuarial_seed = random.randint(1, 2**31 - 1)
        w.save(update_fields=['actuarial_seed', 'updated_at'])
    return int(w.actuarial_seed)


def regenerate_actuarial_seed() -> int:
    w = get_workspace()
    w.actuarial_seed = random.randint(1, 2**31 - 1)
    w.save(update_fields=['actuarial_seed', 'updated_at'])
    return int(w.actuarial_seed)
