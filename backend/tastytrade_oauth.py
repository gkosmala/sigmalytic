
# Copyright (c) 2026 Sigmalytic Quant Corporation.
# Tastytrade OAuth2 — read-only authentication.

import os
import threading
import time

import requests


TOKEN_URL = "https://api.tastyworks.com/oauth/token"
USER_AGENT = "SigmalyticQuant/1.0"


class TastytradeAuthError(RuntimeError):
    pass


class TastytradeOAuth:
    def __init__(self):
        self._access_token = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def get_access_token(self):
        with self._lock:
            if (
                self._access_token
                and time.time() < self._expires_at - 60
            ):
                return self._access_token

            client_id = os.getenv("TASTYTRADE_CLIENT_ID")
            client_secret = os.getenv("TASTYTRADE_CLIENT_SECRET")
            refresh_token = os.getenv("TASTYTRADE_REFRESH_TOKEN")

            if not all([client_id, client_secret, refresh_token]):
                raise TastytradeAuthError(
                    "Tastytrade OAuth environment variables are missing."
                )

            try:
                response = requests.post(
                    TOKEN_URL,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json",
                    },
                    data={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                    },
                    timeout=15,
                )
            except requests.RequestException as exc:
                raise TastytradeAuthError(
                    "Tastytrade authentication network request failed."
                ) from exc

            if response.status_code != 200:
                raise TastytradeAuthError(
                    f"Tastytrade authentication failed "
                    f"(HTTP {response.status_code})."
                )

            try:
                payload = response.json()
                token = payload["access_token"]
                expires_in = int(payload.get("expires_in", 900))
            except (ValueError, KeyError, TypeError) as exc:
                raise TastytradeAuthError(
                    "Tastytrade returned an invalid token response."
                ) from exc

            if not isinstance(token, str) or not token:
                raise TastytradeAuthError(
                    "Tastytrade returned an empty access token."
                )

            self._access_token = token
            self._expires_at = time.time() + expires_in

            return self._access_token


tastytrade_oauth = TastytradeOAuth()
