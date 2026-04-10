"""
Ollama URL / model / timeout overrides stored in WorkspaceState (database).
Falls back to django.conf.settings when not set.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings as django_settings

SESSION_BASE_URL = 'ollama_base_url'
SESSION_MODEL = 'ollama_model'
SESSION_TIMEOUT = 'crew_timeout_sec'


def _trim_url(url: str) -> str:
    u = (url or '').strip().rstrip('/')
    if not u:
        return ''
    if not re.match(r'^https?://', u, re.I):
        return ''
    return u


def normalize_base_url(url: str) -> str:
    """Public: same as internal trim; empty string if invalid."""
    return _trim_url(url)


def get_runtime_config(request) -> dict[str, Any]:
    """Effective Ollama settings for health checks and Crew runs."""
    from . import workspace_state

    workspace_state.migrate_legacy_session(request)
    w = workspace_state.get_workspace()
    base = _trim_url(str(w.ollama_base_url or ''))
    if not base:
        base = django_settings.OLLAMA_BASE_URL.rstrip('/')
    model = (str(w.ollama_model or '').strip() or django_settings.OLLAMA_MODEL)
    raw_to = w.crew_timeout_sec
    try:
        timeout = (
            int(raw_to)
            if raw_to is not None
            else int(django_settings.CREW_RUN_TIMEOUT_SEC)
        )
    except (TypeError, ValueError):
        timeout = int(django_settings.CREW_RUN_TIMEOUT_SEC)
    timeout = max(60, min(3600, timeout))
    from_db = bool(
        _trim_url(str(w.ollama_base_url or ''))
        or (str(w.ollama_model or '').strip())
        or (w.crew_timeout_sec is not None)
    )
    return {
        'base_url': base,
        'model': model,
        'timeout_sec': timeout,
        'from_session': from_db,
        'from_workspace': from_db,
    }


def save_from_post(request, body: dict[str, Any]) -> tuple[bool, str]:
    """Persist optional overrides from JSON body to WorkspaceState."""
    from . import workspace_state

    workspace_state.migrate_legacy_session(request)
    w = workspace_state.get_workspace()
    fields: list[str] = []

    if 'base_url' in body:
        u = _trim_url(str(body.get('base_url') or ''))
        if body.get('base_url') and not u:
            return False, 'Invalid base URL (use http:// or https://)'
        w.ollama_base_url = u
        fields.append('ollama_base_url')

    if 'model' in body:
        m = str(body.get('model') or '').strip()
        if m:
            if len(m) > 120:
                return False, 'Model name too long'
            w.ollama_model = m
        else:
            w.ollama_model = ''
        fields.append('ollama_model')

    if 'timeout_sec' in body:
        t = body.get('timeout_sec')
        if t is None or str(t).strip() == '':
            w.crew_timeout_sec = None
        else:
            try:
                v = int(t)
                v = max(60, min(3600, v))
                w.crew_timeout_sec = v
            except (TypeError, ValueError):
                return False, 'timeout_sec must be an integer'
        fields.append('crew_timeout_sec')

    if fields:
        fields.append('updated_at')
        w.save(update_fields=list(dict.fromkeys(fields)))

    return True, ''


def clear_session_overrides(request) -> None:
    from . import workspace_state

    workspace_state.migrate_legacy_session(request)
    w = workspace_state.get_workspace()
    w.ollama_base_url = ''
    w.ollama_model = ''
    w.crew_timeout_sec = None
    w.save(update_fields=['ollama_base_url', 'ollama_model', 'crew_timeout_sec', 'updated_at'])


def env_defaults() -> dict[str, Any]:
    return {
        'base_url': django_settings.OLLAMA_BASE_URL.rstrip('/'),
        'model': django_settings.OLLAMA_MODEL,
        'timeout_sec': int(django_settings.CREW_RUN_TIMEOUT_SEC),
        'crew_enabled': django_settings.CREW_ANALYSIS_ENABLED,
    }


def _format_size_bytes(n: int | None) -> str:
    if n is None:
        return ''
    try:
        b = float(n)
    except (TypeError, ValueError):
        return ''
    for unit, div in (('GiB', 1024**3), ('MiB', 1024**2), ('KiB', 1024)):
        if b >= div:
            return f'{b / div:.2f} {unit}'
    return f'{int(b)} B'


def fetch_installed_models(
    base_url: str, timeout_sec: float = 10.0
) -> tuple[list[dict[str, Any]], str | None]:
    """
    GET {base}/api/tags — returns sorted list of {name, size, size_label, modified_at}.
    """
    bu = _trim_url(base_url)
    if not bu:
        return [], 'Invalid or empty base URL (use http:// or https://)'
    url = f'{bu}/api/tags'
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return [], f'HTTP {e.code}'
    except urllib.error.URLError as e:
        reason = getattr(e, 'reason', e)
        return [], str(reason)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, TimeoutError) as e:
        return [], str(e)

    models_raw = raw.get('models') or []
    out: list[dict[str, Any]] = []
    for m in models_raw:
        name = (m.get('name') or m.get('model') or '').strip()
        if not name:
            continue
        sz = m.get('size')
        out.append(
            {
                'name': name,
                'size': sz,
                'size_label': _format_size_bytes(sz) if sz is not None else '',
                'modified_at': m.get('modified_at') or '',
            }
        )
    out.sort(key=lambda x: x['name'].lower())
    return out, None
