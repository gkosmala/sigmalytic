
# Copyright (c) 2026 Sigmalytic Quant Corporation.
# Tastytrade OAuth diagnostic — read-only, no trading.

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import hmac
import os

from backend.tastytrade_oauth import (
    tastytrade_oauth,
    TastytradeAuthError,
)

router = APIRouter(prefix="/api/internal/tastytrade")
security = HTTPBearer(auto_error=False)


def require_diagnostic_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    expected = os.getenv("TASTYTRADE_DIAGNOSTIC_KEY", "")

    if (
        not expected
        or credentials is None
        or credentials.scheme.lower() != "bearer"
        or not hmac.compare_digest(credentials.credentials, expected)
    ):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/auth-check")
def tastytrade_auth_check(
    _=Depends(require_diagnostic_key),
):
    try:
        tastytrade_oauth.get_access_token()
        return {
            "provider": "tastytrade",
            "authentication": "success",
            "mode": "read_only",
        }
    except TastytradeAuthError:
        return {
            "provider": "tastytrade",
            "authentication": "failed",
            "mode": "read_only",
        }
    except Exception:
        return {
            "provider": "tastytrade",
            "authentication": "error",
            "mode": "read_only",
        }
