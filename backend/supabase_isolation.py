# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/supabase_isolation.py
------------------------------
Per-user Supabase client dependency for FastAPI.

HOW IT WORKS
────────────
- Real users: Dash passes their Supabase JWT as Authorization: Bearer <token>
  FastAPI verifies the token's signature (not just its contents) using the
  project's Supabase JWT secret, then uses the verified 'sub' claim as the
  user's identity.

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
in it, and rejecting (401) rather than silently downgrading to demo when
a JWT-shaped token fails verification.

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

import os
import logging
from fastapi import Request, HTTPException

log = logging.getLogger("supabase_isolation")

DEMO_USER_ID = "demo_user_001"

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


def get_user_id_from_request(request: Request) -> str:
    """
    FastAPI dependency — extracts and verifies user_id from the Authorization header.

    - Missing header, or the literal sentinel "demo": returns DEMO_USER_ID.
    - Present and a valid, signature-verified Supabase JWT: returns the
      real user UUID from the verified 'sub' claim.
    - Present but fails verification (forged, expired, wrong secret):
      raises 401. This is deliberate -- silently falling back to demo
      here would hide bugs and, more importantly, would mean a bad actor
      could probe the API with garbage tokens with no signal anything
      was wrong.
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return DEMO_USER_ID

    token = auth_header.split(" ", 1)[1].strip()
    if not token or token == "demo":
        return DEMO_USER_ID

    if not SUPABASE_JWT_SECRET:
        # Fail closed, not open: if we can't verify signatures at all,
        # we must not trust any non-demo token's claimed identity.
        log.error("SUPABASE_JWT_SECRET not configured — rejecting authenticated request")
        raise HTTPException(503, "Authentication is not configured on this server")

    try:
        import jwt as pyjwt

        payload = pyjwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except Exception as e:
        log.warning(f"JWT verification failed: {e}")
        raise HTTPException(401, "Invalid or expired session — please log in again")

    user_id = payload.get("sub", "")
    if not user_id:
        raise HTTPException(401, "Invalid session token")

    log.debug(f"Authenticated user: {user_id[:8]}…")
    return user_id


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
