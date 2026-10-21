"""Opaque browser sessions; no client-selected identity is trusted.

Prototype sessions are bearer capabilities, not verified insurance identities.
"""
from fastapi import HTTPException, Request
from .runtime import get_runtime

COOKIE = 'omnicare_session'


def session_owner(request: Request) -> str:
    origin = request.headers.get('origin')
    from .config import settings
    if origin and origin not in settings.cors_origin_list and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Origin not allowed')
    auth = request.headers.get('authorization', '')
    token = auth.removeprefix('Bearer ') if auth.startswith('Bearer ') else request.cookies.get(COOKIE, '')
    owner = get_runtime().db.session_owner(token)
    if not owner:
        raise HTTPException(401, 'Your session expired. Reload to start a new session.')
    return owner
