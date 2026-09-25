"""Authentication stays isolated when Supabase changes JWT signing keys."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from backend import supabase_isolation as auth


def request(token=None):
    return SimpleNamespace(headers={"Authorization": f"Bearer {token}"} if token else {})


class SupabaseAuthFallbackTests(unittest.TestCase):
    def test_verified_user_from_auth_server_when_legacy_secret_is_absent(self):
        response = SimpleNamespace(status_code=200, ok=True,
                                   json=lambda: {"id": "verified-user"})
        settings = {"SUPABASE_URL": "https://project.example", "SUPABASE_ANON_KEY": "public-key"}
        with patch.dict(os.environ, settings), patch.object(auth, "SUPABASE_JWT_SECRET", ""), \
                patch.object(auth.requests, "get", return_value=response) as get:
            self.assertEqual(auth.get_user_id_from_request(request("new.signed.token")),
                             "verified-user")
            get.assert_called_once_with(
                "https://project.example/auth/v1/user",
                headers={"apikey": "public-key", "Authorization": "Bearer new.signed.token"},
                timeout=8,
            )

    def test_invalid_token_never_becomes_a_demo_or_arbitrary_user(self):
        response = SimpleNamespace(status_code=401, ok=False)
        settings = {"SUPABASE_URL": "https://project.example", "SUPABASE_ANON_KEY": "public-key"}
        with patch.dict(os.environ, settings), patch.object(auth, "SUPABASE_JWT_SECRET", ""), \
                patch.object(auth.requests, "get", return_value=response):
            with self.assertRaises(HTTPException) as failed:
                auth.get_user_id_from_request(request("forged.user.token"))
        self.assertEqual(failed.exception.status_code, 401)

    def test_auth_server_must_return_a_verified_identity(self):
        response = SimpleNamespace(status_code=200, ok=True, json=lambda: {"id": ""})
        settings = {"SUPABASE_URL": "https://project.example", "SUPABASE_ANON_KEY": "public-key"}
        with patch.dict(os.environ, settings), patch.object(auth, "SUPABASE_JWT_SECRET", ""), \
                patch.object(auth.requests, "get", return_value=response):
            with self.assertRaises(HTTPException) as failed:
                auth.get_user_id_from_request(request("missing.user.token"))
        self.assertEqual(failed.exception.status_code, 503)

    def test_demo_and_malformed_tokens_do_not_call_auth_server(self):
        with patch.object(auth.requests, "get") as get:
            self.assertEqual(auth.get_user_id_from_request(request()), "demo_user_001")
            with self.assertRaises(HTTPException) as failed:
                auth.get_user_id_from_request(request("not-a-jwt"))
            self.assertEqual(failed.exception.status_code, 401)
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
