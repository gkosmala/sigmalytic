from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "backend" / "trade_journal_service.py"
API = ROOT / "backend" / "trade_journal_api.py"
MAIN = ROOT / "backend" / "main.py"

def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def _function_body(source: str, name: str) -> str:
    start = source.index(f"def {name}(")
    match = re.search(r"\ndef [A-Za-z_][A-Za-z0-9_]*\(", source[start + 1:])
    if not match:
        return source[start:]
    return source[start:start + 1 + match.start()]

def test_trade_journal_service_has_supabase_client():
    source = _text(SERVICE)
    assert "def _supabase(" in source
    assert "SUPABASE_URL = os.getenv" in source
    assert "SUPABASE_KEY =" in source

def test_active_journal_functions_do_not_call_legacy_db_path():
    source = _text(SERVICE)
    for name in [
        "log_trade_entry",
        "log_trade_exit",
        "get_journal_entries",
        "get_trader_profile",
        "_update_trader_profile",
    ]:
        body = _function_body(source, name)
        assert "_supabase(" in body, name
        assert "_db(" not in body, name
        assert "_ensure_tables(" not in body, name
        assert "psycopg2" not in body, name
        assert "DATABASE_URL" not in body, name

def test_journal_router_defines_expected_routes():
    source = _text(API)
    assert 'journal_router = APIRouter(prefix="/api/journal"' in source
    assert '@journal_router.post("/entry")' in source
    assert '@journal_router.post("/exit/{journal_id}")' in source
    assert '@journal_router.get("/trades")' in source
    assert '@journal_router.get("/open")' in source
    assert '@journal_router.get("/profile")' in source

def test_main_mounts_journal_router():
    source = _text(MAIN)
    assert "SIGMALYTIC TRADE JOURNAL ROUTER MOUNT START" in source
    assert "from backend.trade_journal_api import journal_router" in source
    assert "app.include_router(journal_router)" in source
    assert '"/api/journal/mount-status"' in source

if __name__ == "__main__":
    test_trade_journal_service_has_supabase_client()
    test_active_journal_functions_do_not_call_legacy_db_path()
    test_journal_router_defines_expected_routes()
    test_main_mounts_journal_router()
    print("STATIC_TESTS_PASS")

def test_trader_profile_payload_matches_schema_fields():
    source = _text(SERVICE)
    for field in [
        '"avg_entry_quality"',
        '"avg_exit_quality"',
        '"entry_grade_dist"',
        '"exit_grade_dist"',
        '"behavioral_trend"',
        '"strongest_pattern"',
        '"weakest_pattern"',
    ]:
        assert field in source, field
