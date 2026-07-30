"""
tests/conftest.py
------------------
Sets placeholder environment variables required for backend/frontend
modules to import cleanly in a test environment, before any test
collection happens. These modules read real credentials at import time
(Supabase, Alpaca, Resend) -- tests never make real network calls, but
the modules need *something* present in these env vars to avoid
crashing during import.

This mirrors exactly the pattern used throughout the July 30, 2026
debugging session to safely import and verify these modules locally.
"""
import os

os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "placeholder")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "placeholder")
os.environ.setdefault("ALPACA_API_KEY_ID", "placeholder")
os.environ.setdefault("ALPACA_API_SECRET_KEY", "placeholder")
os.environ.setdefault("ALPACA_API_KEY", "placeholder")
os.environ.setdefault("ALPACA_API_SECRET", "placeholder")
os.environ.setdefault("RESEND_API_KEY", "placeholder")
