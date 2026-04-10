"""
Organization branding for crew reports — persisted in OrganizationProfile (singleton pk=1).

Legacy session key SESSION_COMPANY_PROFILE_KEY is read once and migrated into the DB when present.
"""
from __future__ import annotations

from typing import Any

from django.apps import apps

SESSION_COMPANY_PROFILE_KEY = 'company_profile'

MAX_COMPANY_NAME = 200
MAX_LEGAL_NAME = 200
MAX_ADDRESS = 500
MAX_CITY = 120
MAX_REGION = 120
MAX_POSTAL = 32
MAX_COUNTRY = 120
MAX_PHONE = 80
MAX_EMAIL = 120
MAX_WEBSITE = 500
MAX_LOGO_URL = 500
MAX_TAGLINE = 300


def _trim(s: str | None, max_len: int) -> str:
    if not s:
        return ''
    return str(s).strip()[:max_len]


def _is_reasonable_url(url: str) -> bool:
    if not url:
        return True
    u = url.strip().lower()
    return u.startswith('http://') or u.startswith('https://')


def default_company_profile() -> dict[str, str]:
    return {
        'company_name': '',
        'legal_name': '',
        'address': '',
        'city': '',
        'region': '',
        'postal_code': '',
        'country': '',
        'phone': '',
        'email': '',
        'website': '',
        'logo_url': '',
        'tagline': '',
    }


def _caps() -> dict[str, int]:
    return {
        'company_name': MAX_COMPANY_NAME,
        'legal_name': MAX_LEGAL_NAME,
        'address': MAX_ADDRESS,
        'city': MAX_CITY,
        'region': MAX_REGION,
        'postal_code': MAX_POSTAL,
        'country': MAX_COUNTRY,
        'phone': MAX_PHONE,
        'email': MAX_EMAIL,
        'website': MAX_WEBSITE,
        'logo_url': MAX_LOGO_URL,
        'tagline': MAX_TAGLINE,
    }


def _row_to_dict(row: Any) -> dict[str, str]:
    out = default_company_profile()
    caps = _caps()
    if row is None:
        return out
    for k in out:
        raw = getattr(row, k, None)
        if raw is None:
            continue
        out[k] = _trim(str(raw), caps[k])
    return out


def _migrate_session_to_db(request) -> None:
    """One-time lift: if DB is empty but session had legacy branding, persist and drop session."""
    OrganizationProfile = apps.get_model('actuarial', 'OrganizationProfile')
    row = OrganizationProfile.objects.filter(pk=1).first()
    db_empty = row is None or not any(
        (_trim(str(getattr(row, k, '') or ''), _caps()[k]) for k in default_company_profile())
    )
    if not db_empty:
        return
    raw = request.session.get(SESSION_COMPANY_PROFILE_KEY)
    if not isinstance(raw, dict):
        return
    caps = _caps()
    prof = default_company_profile()
    for k in prof:
        if k in raw and isinstance(raw[k], str):
            prof[k] = _trim(raw[k], caps[k])
    if not any(prof.values()):
        return
    OrganizationProfile.objects.update_or_create(
        pk=1,
        defaults={k: prof[k] for k in prof},
    )
    request.session.pop(SESSION_COMPANY_PROFILE_KEY, None)
    request.session.modified = True


def get_company_profile(request) -> dict[str, str]:
    _migrate_session_to_db(request)
    OrganizationProfile = apps.get_model('actuarial', 'OrganizationProfile')
    row = OrganizationProfile.objects.filter(pk=1).first()
    return _row_to_dict(row)


def set_company_profile(request, data: dict[str, Any]) -> tuple[bool, str]:
    """Validate and save to the database; returns (ok, error_message)."""
    OrganizationProfile = apps.get_model('actuarial', 'OrganizationProfile')
    prof = default_company_profile()
    caps = _caps()
    for k in prof:
        if k not in data:
            continue
        val = data[k]
        if val is None:
            continue
        if not isinstance(val, str):
            return False, f'Invalid type for {k}'
        t = _trim(val, caps[k])
        if k == 'logo_url' and t and not _is_reasonable_url(t):
            return False, 'logo_url must start with http:// or https://'
        if k == 'website' and t and not _is_reasonable_url(t):
            return False, 'website must start with http:// or https://'
        prof[k] = t

    if not any(v for v in prof.values()):
        OrganizationProfile.objects.filter(pk=1).delete()
    else:
        OrganizationProfile.objects.update_or_create(pk=1, defaults={k: prof[k] for k in prof})

    request.session.pop(SESSION_COMPANY_PROFILE_KEY, None)
    request.session.modified = True
    return True, ''


def clear_company_profile(request) -> None:
    OrganizationProfile = apps.get_model('actuarial', 'OrganizationProfile')
    OrganizationProfile.objects.filter(pk=1).delete()
    request.session.pop(SESSION_COMPANY_PROFILE_KEY, None)
    request.session.modified = True


def format_company_profile_for_crew(request) -> str:
    """Structured block for kickoff and {company_profile} token; empty if unset."""
    p = get_company_profile(request)
    if not any(v.strip() for v in p.values()):
        return ''
    lines: list[str] = [
        '=== Organization / report branding (use for letterhead, title block, footer) ===',
    ]
    if p['company_name']:
        lines.append(f"Company name: {p['company_name']}")
    if p['legal_name']:
        lines.append(f"Legal name: {p['legal_name']}")
    if p['tagline']:
        lines.append(f"Tagline / report subtitle: {p['tagline']}")
    addr_parts = [
        x
        for x in (
            p['address'],
            p['city'],
            p['region'],
            p['postal_code'],
            p['country'],
        )
        if x.strip()
    ]
    if addr_parts:
        lines.append('Address: ' + ', '.join(addr_parts))
    if p['phone']:
        lines.append(f"Phone: {p['phone']}")
    if p['email']:
        lines.append(f"Email: {p['email']}")
    if p['website']:
        lines.append(f"Website: {p['website']}")
    if p['logo_url']:
        lines.append(
            f"Logo image URL (reference in report header if appropriate): {p['logo_url']}"
        )
    lines.append('=== End organization branding ===')
    return '\n'.join(lines)


def company_profile_plain_for_tasks(request) -> str:
    """Same content as format_company_profile_for_crew for task template token."""
    return format_company_profile_for_crew(request)
