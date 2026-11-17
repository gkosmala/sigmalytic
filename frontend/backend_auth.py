"""
frontend/backend_auth.py — adds Sigmalytic's backend key to every request the
frontend sends to the backend, without touching any other code.

Imported once at the top of frontend/app.py. Reads SUBSCRIBER_TOKEN from the
Render settings; if it isn't set, it does nothing.
"""

import os
from urllib.parse import urlparse

import requests

_TOKEN = os.getenv("SUBSCRIBER_TOKEN", "")
_HEADER = "X-Sigmalytic-Key"

# Backend hosts that should receive the key (never sent anywhere else).
_HOSTS = {"sigmalytic-backend.onrender.com", "localhost", "127.0.0.1"}
for _var in ("BACKEND_URL", "API_URL", "API_BASE_URL", "BACKEND_API_URL"):
    _val = os.getenv(_var, "")
    if _val:
        _HOSTS.add(urlparse(_val if "://" in _val else "https://" + _val).hostname or "")

_original_request = requests.Session.request


def _request_with_key(self, method, url, *args, **kwargs):
    try:
        host = urlparse(str(url)).hostname or ""
        if _TOKEN and (host in _HOSTS or host.startswith("sigmalytic-backend")):
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault(_HEADER, _TOKEN)
            kwargs["headers"] = headers
    except Exception:
        pass  # never let this helper break a request
    return _original_request(self, method, url, *args, **kwargs)


if not getattr(requests.Session.request, "_sigmalytic_key", False):
    _request_with_key._sigmalytic_key = True
    requests.Session.request = _request_with_key
