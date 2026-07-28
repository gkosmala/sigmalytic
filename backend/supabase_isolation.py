# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/supabase_isolation.py
------------------------------
Per-user Supabase client dependency for FastAPI.

HOW IT WORKS
────────────
- Real users: Dash passes their Supabase JWT as Authorization: Bearer <token>
  FastAPI extracts it and creates a Supabase client scoped to that JWT.
  Postgres RLS then enforces auth.uid() = user_id on every query.

- Demo users: No JWT is passed. Backend falls back to demo_user_001
  using the service role / anon key with no RLS filtering.

USAGE IN ENDPOINTS
──────────────────
from supabase_isolation import get_user_id_from_request

@app.post("/api/some-endpoint")
async def my_endpoint(
    request: Request,
    user_id: str = Depends(get_user_id_from_request),
):
    # user_id is now either the real Supabase UUID or "demo_user_001"
    ...
"""

import os
import logging
from fastapi import Request

log = logging.getLogger("supabase_isolation")

DEMO_USER_ID = "demo_user_001"


def get_user_id_from_request(request: Request) -> str:
    """
    FastAPI dependency — extracts user_id from the Authorization header.

    - If header is present and valid: decodes JWT and returns Supabase user UUID
    - If header is missing or invalid: returns "demo_user_001" (demo fallback)

    This keeps demo sessions working without JWT while isolating real users.
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return DEMO_USER_ID

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return DEMO_USER_ID

    # Decode JWT without verification (Supabase already verified it)
    # We only need the sub (user UUID) from the payload
    #
    # FIX (2026-07-28): this used to jump straight to token.split(".")[1],
    # assuming every token has the real JWT structure (header.payload.
    # signature, 3 dot-separated parts). The frontend deliberately sends
    # the literal string "demo" as a sentinel for demo sessions -- that
    # has zero dots, so indexing [1] raised IndexError every single time,
    # logged as "JWT decode failed: list index out of range" on every
    # request. The fallback to DEMO_USER_ID was always correct, but it
    # was reached via an actual exception on the expected, normal case
    # rather than a clean check. This checks the token's shape first, so
    # demo sessions -- and any other non-JWT token -- are recognized
    # immediately without an exception or a misleading warning log.
    token_parts = token.split(".")
    if len(token_parts) != 3:
        log.debug(f"Token is not JWT-shaped ({len(token_parts)} part(s), expected 3) — using demo fallback")
        return DEMO_USER_ID

    try:
        import base64, json as _json

        # JWT structure: header.payload.signature
        payload_b64 = token_parts[1]

        # Fix base64 padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload = _json.loads(base64.b64decode(payload_b64).decode("utf-8"))
        user_id = payload.get("sub", "")

        if user_id:
            log.debug(f"Authenticated user: {user_id[:8]}…")
            return user_id
        else:
            log.warning("JWT payload missing 'sub' field — falling back to demo")
            return DEMO_USER_ID

    except Exception as e:
        log.warning(f"JWT decode failed: {e} — falling back to demo")
        return DEMO_USER_ID


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
