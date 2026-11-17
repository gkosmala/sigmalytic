"""
backend/security.py — lock down Sigmalytic's backend.

Wire it up in backend/main.py:

    from backend.security import create_app_kwargs, install_security

    app = FastAPI(**create_app_kwargs())   # replaces your current FastAPI(...) call
    install_security(app)                  # call right after the app is created

Round 1 (safe, automatic on Render): debug routes and API docs disappear;
nothing else changes.

Round 2 (later, once the frontend and cron jobs send tokens), also set:
    STRICT_MODE=1
    ADMIN_TOKEN=<long random string; e.g. python -c "import secrets;print(secrets.token_urlsafe(48))">
    SUBSCRIBER_TOKEN=<separate long random string>   # interim, until per-user auth exists
    ALLOWED_ORIGINS=https://sigmalytic-frontend.onrender.com
"""

import os
import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Render sets RENDER=true on every service, so production is detected automatically.
IS_PROD = os.getenv("APP_ENV") == "production" or os.getenv("RENDER") == "true"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
SUBSCRIBER_TOKEN = os.getenv("SUBSCRIBER_TOKEN", "")

# Path prefixes and the token each one requires.
# Order matters: the first matching prefix wins.
PROTECTED_PREFIXES = [
    ("/api/debug", "admin"),           # debug: admin only (or remove entirely in prod)
    ("/api/admin", "admin"),           # belt-and-braces on top of your existing check
    ("/api/scoreboard", "subscriber"),  # full track-record detail: paying users only
    ("/api/campaigns", "subscriber"),
    ("/api/radar", "subscriber"),
    ("/api/weis-radar", "subscriber"),
    ("/api/research", "subscriber"),
    ("/api/journal", "subscriber"),
    ("/api/behavior", "subscriber"),
    ("/api/portfolio", "subscriber"),
]

# Until STRICT_MODE=1 is set in Render, ONLY debug routes are locked.
# That keeps the frontend, admin panel and cron jobs working exactly as today.
if os.getenv("STRICT_MODE", "0") != "1":
    PROTECTED_PREFIXES = [("/api/debug", "admin")]

# Endpoints that stay public on purpose (marketing / health checks).
PUBLIC_EXACT = {"/", "/health", "/api/health", "/api/scoreboard/public-summary"}


def create_app_kwargs() -> dict:
    """Turn off /docs, /redoc and /openapi.json in production."""
    if IS_PROD:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


def _token_ok(presented: str, expected: str) -> bool:
    # Fail closed if the env var is missing; constant-time compare.
    return bool(expected) and bool(presented) and secrets.compare_digest(presented, expected)


def install_security(app: FastAPI) -> None:
    # CORS is only tightened once ALLOWED_ORIGINS is set, so nothing breaks before then.
    origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def gatekeeper(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path in PUBLIC_EXACT:
            return await call_next(request)

        for prefix, level in PROTECTED_PREFIXES:
            if path.startswith(prefix):
                # In production, debug routes simply don't exist.
                if IS_PROD and prefix == "/api/debug":
                    return JSONResponse({"detail": "Not Found"}, status_code=404)

                auth = request.headers.get("Authorization", "")
                token = auth.removeprefix("Bearer ").strip()
                allowed = _token_ok(token, ADMIN_TOKEN) or (
                    level == "subscriber" and _token_ok(token, SUBSCRIBER_TOKEN)
                )
                if not allowed:
                    return JSONResponse({"detail": "Unauthorized"}, status_code=401)
                break

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
