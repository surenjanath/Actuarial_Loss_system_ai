"""Signed tokens for read-only board display URLs (TV / shared screen)."""
from __future__ import annotations

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

BOARD_TOKEN_SALT = 'actuarial.crew.board'
# 7 days; refresh link from run detail if needed.
BOARD_TOKEN_MAX_AGE = 7 * 24 * 3600


def sign_board_token(run_id) -> str:
    return TimestampSigner(salt=BOARD_TOKEN_SALT).sign(str(run_id))


class BoardTokenError(Exception):
    pass


def parse_board_token(token: str) -> str:
    """Return run_id string or raise BoardTokenError."""
    try:
        raw = TimestampSigner(salt=BOARD_TOKEN_SALT).unsign(token, max_age=BOARD_TOKEN_MAX_AGE)
    except SignatureExpired as e:
        raise BoardTokenError('Token expired') from e
    except BadSignature as e:
        raise BoardTokenError('Invalid token') from e
    if isinstance(raw, bytes):
        return raw.decode()
    return str(raw)
