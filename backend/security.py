"""
backend/security.py — lock down Sigmalytic's backend.

Already wired into backend/main.py:
    app = FastAPI(..., **create_app_kwargs())
    install_security(app)

Render settings (sigmalytic-backend):
    STRICT_MODE      unset / "0"  -> only debug routes + API docs are hidden
                     "report"     -> ALSO log every signal-data request that has no key
                                     ("[security] WOULD BLOCK ..."), but let it through
                     "1"          -> block signal-data requests that have no key (401)
    SUBSCRIBER_TOKEN shared secret; the frontend sends it as the X-Sigmalytic-Key header
                     (see frontend/backend_auth.py). Must match on both services.

Admin routes (/api/admin/...) are NOT touched here: they keep their existing protection.
"""

import os
import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Render sets RENDER=true on every service, so production is detected automatically.
IS_PROD = os.getenv("APP_ENV") == "production" or os.getenv("RENDER") == "true"
STRICT_MODE = os.getenv("STRICT_MODE", "0").strip().lower()
SUBSCRIBER_TOKEN = os.getenv("SUBSCRIBER_TOKEN", "")
KEY_HEADER = "X-Sigmalytic-Key"

# Signal / track-record data: only callers holding the key may read it.
PROTECTED_PREFIXES = (
    "/api/scoreboard",
    "/api/campaigns",
    "/api/radar",
    "/api/weis-radar",
    "/api/research",
    "/api/journal",
    "/api/behavior",
    "/api/portfolio",
    "/api/reports",
    "/api/morning-report",
    "/api/options",
    "/api/heatmap",
)


def create_app_kwargs() -> dict:
    """Turn off /docs, /redoc and /openapi.json in production."""
    if IS_PROD:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


def _has_valid_key(request: Request) -> bool:
    presented = request.headers.get(KEY_HEADER, "")
    return bool(SUBSCRIBER_TOKEN) and bool(presented) and secrets.compare_digest(presented, SUBSCRIBER_TOKEN)


def install_security(app: FastAPI) -> None:
    # CORS is only tightened once ALLOWED_ORIGINS is set, so nothing breaks before then.
    origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", KEY_HEADER],
        )

    @app.middleware("http")
    async def gatekeeper(request: Request, call_next):
        path = request.url.path

        # Debug routes don't exist in production.
        if IS_PROD and path.startswith("/api/debug"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        if request.method != "OPTIONS" and path.startswith(PROTECTED_PREFIXES) and not _has_valid_key(request):
            if STRICT_MODE == "1":
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            if STRICT_MODE == "report":
                ua = request.headers.get("user-agent", "-")
                print(f"[security] WOULD BLOCK {request.method} {path} ua={ua}", flush=True)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
