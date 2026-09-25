# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/supabase_isolation.py
------------------------------
Per-user Supabase client dependency for FastAPI.

HOW IT WORKS
────────────
- Real users: Dash passes their Supabase JWT as Authorization: Bearer <token>.
  The backend verifies legacy tokens with the configured secret, or asks
  this project's Supabase Auth server to verify other signing keys. It
  trusts only the verified user id returned by either path.

- Demo users: No JWT is passed (or the literal sentinel "demo" is sent).
  Backend falls back to demo_user_001.

SECURITY FIX (2026-07-28): this previously base64-decoded the JWT payload
and trusted whatever 'sub' claim was inside it WITHOUT verifying the
signature at all -- the comment here used to say "Supabase already
verified it," but nothing in this code path actually checked that. Anyone
could construct a fake token with any 'sub' (user UUID) they wanted and
the backend would treat the request as that user, since preferences,
journal, and behavior endpoints use the Supabase *service role* key
(which bypasses Postgres RLS) keyed off whatever user_id this function
returned. This is a real account-isolation vulnerability: one user could
read or write another user's data. Fixed by actually verifying the
token's signature against SUPABASE_JWT_SECRET (Supabase dashboard ->
Settings -> API -> JWT Settings -> JWT Secret) before trusting anything
in it, and rejecting rather than silently downgrading to demo when a
JWT-shaped token fails verification. Supabase Auth now verifies tokens
that cannot be checked with the legacy secret.

USAGE IN ENDPOINTS
──────────────────
from supabase_isolation import get_user_id_from_request

@app.post("/api/some-endpoint")
async def my_endpoint(
    request: Request,
    user_id: str = Depends(get_user_id_from_request),
):
    # user_id is now either a cryptographically verified Supabase UUID,
    # or "demo_user_001" for demo sessions.
    ...
"""

import logging
import os

import requests
from fastapi import Request, HTTPException

log = logging.getLogger("supabase_isolation")

DEMO_USER_ID = "demo_user_001"

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


def _verified_user_id_from_auth_server(token: str) -> str:
    """Ask this project's Supabase Auth service to validate a user's token.

    This also supports asymmetric signing keys and deployments without the
    legacy JWT secret. Never use the unverified JWT payload as an identity.
    """
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    api_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not api_key:
        log.error("Supabase Auth verification is not configured")
        raise HTTPException(503, "Authentication is not configured on this server")

    try:
        response = requests.get(
            f"{url}/auth/v1/user",
            headers={"apikey": api_key, "Authorization": f"Bearer {token}"},
            timeout=8,
        )
    except requests.RequestException as exc:
        log.warning("Supabase Auth verification unavailable: %s", type(exc).__name__)
        raise HTTPException(503, "Authentication service unavailable") from exc

    if response.status_code in (401, 403):
        raise HTTPException(401, "Invalid or expired session — please log in again")
    if not response.ok:
        log.warning("Supabase Auth verification returned status %s", response.status_code)
        raise HTTPException(503, "Authentication service unavailable")

    try:
        user_id = response.json().get("id")
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(503, "Authentication service returned an invalid response") from exc
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(503, "Authentication service returned an invalid response")
    return user_id


def get_user_id_from_request(request: Request) -> str:
    """
    FastAPI dependency — extracts and verifies user_id from the Authorization header.

    - Missing header, or the literal sentinel "demo": returns DEMO_USER_ID.
    - A locally verifiable legacy token uses the configured HS256 secret.
    - Other tokens are checked by Supabase Auth, which supports rotating
      signing keys and verifies the current project's user identity.
    - Invalid tokens never fall back to the shared demo account.
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return DEMO_USER_ID

    token = auth_header.split(" ", 1)[1].strip()
    if not token or token == "demo":
        return DEMO_USER_ID

    if token.count(".") != 2:
        raise HTTPException(401, "Invalid session token")

    if SUPABASE_JWT_SECRET:
        try:
            import jwt as pyjwt

            payload = pyjwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except pyjwt.PyJWTError:
            # A rotated/asymmetric signing key cannot be verified with the
            # old shared secret. Let Supabase Auth decide if it is valid.
            pass
        else:
            user_id = payload.get("sub")
            if not isinstance(user_id, str) or not user_id:
                raise HTTPException(401, "Invalid session token")
            return user_id

    return _verified_user_id_from_auth_server(token)


def get_auth_headers(session: dict) -> dict:
    """
    Helper for Dash frontend callbacks.
    Builds the Authorization header dict from the session store.

    Usage in app.py:
        from supabase_isolation import get_auth_headers
        headers = get_auth_headers(session)
        r = requests.get(f"{BACKEND_HTTP}/api/...", headers=headers)
    """
    if not session:
        return {}
    token = session.get("access_token", "")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}
