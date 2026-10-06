# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/broker_vault_store.py
-----------------------------
Per-user storage for the five broker vaults. Two interchangeable stores:
SupabaseVaultStore (production) and MemoryVaultStore (tests). Every call is
scoped by user_id so one user can never read another's statements.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SLOTS = (1, 2, 3, 4, 5)
MAX_ROWS_PER_STATEMENT = 20000
MAX_STATEMENTS_PER_VAULT = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VaultError(Exception):
    pass


def check_slot(slot: int) -> int:
    if slot not in SLOTS:
        raise VaultError("Vault slot must be 1 to 5.")
    return slot


class MemoryVaultStore:
    def __init__(self) -> None:
        self.vaults: Dict[tuple, Dict[str, Any]] = {}
        self.statements: Dict[str, Dict[str, Any]] = {}

    def list_vaults(self, user_id: str) -> List[Dict[str, Any]]:
        out = []
        for slot in SLOTS:
            v = self.vaults.get((user_id, slot))
            sts = [s for s in self.statements.values() if s["user_id"] == user_id and s["slot"] == slot]
            out.append({
                "slot": slot,
                "name": (v or {}).get("name", ""),
                "broker": (v or {}).get("broker", ""),
                "statements": len(sts),
                "rows": sum(s["row_count"] for s in sts),
            })
        return out

    def upsert_vault(self, user_id: str, slot: int, name: str, broker: str) -> None:
        check_slot(slot)
        self.vaults[(user_id, slot)] = {"name": name, "broker": broker}

    def add_statement(self, user_id: str, slot: int, record: Dict[str, Any]) -> str:
        check_slot(slot)
        if len(record.get("rows", [])) > MAX_ROWS_PER_STATEMENT:
            raise VaultError(f"A statement can hold at most {MAX_ROWS_PER_STATEMENT} rows.")
        count = sum(1 for s in self.statements.values() if s["user_id"] == user_id and s["slot"] == slot)
        if count >= MAX_STATEMENTS_PER_VAULT:
            raise VaultError(f"A vault can hold at most {MAX_STATEMENTS_PER_VAULT} statements.")
        sid = "bst_" + uuid.uuid4().hex[:14]
        self.statements[sid] = {**record, "statement_id": sid, "user_id": user_id, "slot": slot,
                                "uploaded_at": _now()}
        return sid

    def list_statements(self, user_id: str, slot: int, with_rows: bool = False) -> List[Dict[str, Any]]:
        check_slot(slot)
        out = [s for s in self.statements.values() if s["user_id"] == user_id and s["slot"] == slot]
        out.sort(key=lambda s: s["uploaded_at"])
        if not with_rows:
            out = [{k: v for k, v in s.items() if k != "rows"} for s in out]
        return out

    def delete_statement(self, user_id: str, statement_id: str) -> bool:
        s = self.statements.get(statement_id)
        if not s or s["user_id"] != user_id:
            return False
        del self.statements[statement_id]
        return True

    def clear_vault(self, user_id: str, slot: int) -> int:
        check_slot(slot)
        ids = [i for i, s in self.statements.items() if s["user_id"] == user_id and s["slot"] == slot]
        for i in ids:
            del self.statements[i]
        self.vaults.pop((user_id, slot), None)
        return len(ids)


class SupabaseVaultStore:
    def __init__(self, client: Any) -> None:
        self.sb = client

    @staticmethod
    def _rows(res: Any) -> List[Dict[str, Any]]:
        data = getattr(res, "data", None)
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []

    def list_vaults(self, user_id: str) -> List[Dict[str, Any]]:
        vaults = {r["slot"]: r for r in self._rows(
            self.sb.table("broker_vaults").select("slot,name,broker").eq("user_id", user_id).execute())}
        sts = self._rows(self.sb.table("broker_statements")
                         .select("slot,row_count").eq("user_id", user_id).execute())
        out = []
        for slot in SLOTS:
            mine = [s for s in sts if s["slot"] == slot]
            v = vaults.get(slot, {})
            out.append({"slot": slot, "name": v.get("name", ""), "broker": v.get("broker", ""),
                        "statements": len(mine), "rows": sum(int(s.get("row_count") or 0) for s in mine)})
        return out

    def upsert_vault(self, user_id: str, slot: int, name: str, broker: str) -> None:
        check_slot(slot)
        self.sb.table("broker_vaults").upsert(
            {"user_id": user_id, "slot": slot, "name": name, "broker": broker, "updated_at": _now()},
            on_conflict="user_id,slot").execute()

    def add_statement(self, user_id: str, slot: int, record: Dict[str, Any]) -> str:
        check_slot(slot)
        if len(record.get("rows", [])) > MAX_ROWS_PER_STATEMENT:
            raise VaultError(f"A statement can hold at most {MAX_ROWS_PER_STATEMENT} rows.")
        existing = self._rows(self.sb.table("broker_statements").select("statement_id")
                              .eq("user_id", user_id).eq("slot", slot).execute())
        if len(existing) >= MAX_STATEMENTS_PER_VAULT:
            raise VaultError(f"A vault can hold at most {MAX_STATEMENTS_PER_VAULT} statements.")
        sid = "bst_" + uuid.uuid4().hex[:14]
        self.sb.table("broker_statements").insert({**record, "statement_id": sid, "user_id": user_id,
                                                   "slot": slot}).execute()
        return sid

    def list_statements(self, user_id: str, slot: int, with_rows: bool = False) -> List[Dict[str, Any]]:
        check_slot(slot)
        cols = ("statement_id,filename,kind,row_count,period_start,period_end,uploaded_at"
                + (",rows" if with_rows else ""))
        return self._rows(self.sb.table("broker_statements").select(cols)
                          .eq("user_id", user_id).eq("slot", slot).order("uploaded_at").execute())

    def delete_statement(self, user_id: str, statement_id: str) -> bool:
        res = self.sb.table("broker_statements").delete().eq("user_id", user_id) \
            .eq("statement_id", statement_id).execute()
        return bool(self._rows(res))

    def clear_vault(self, user_id: str, slot: int) -> int:
        check_slot(slot)
        res = self.sb.table("broker_statements").delete().eq("user_id", user_id).eq("slot", slot).execute()
        self.sb.table("broker_vaults").delete().eq("user_id", user_id).eq("slot", slot).execute()
        return len(self._rows(res))


def default_store() -> Any:
    """Supabase store using the same env keys as the journal."""
    url = os.getenv("SUPABASE_URL", "")
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
           or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "")
    if not url or not key:
        raise VaultError("Vault storage is not configured on this server.")
    from supabase import create_client
    return SupabaseVaultStore(create_client(url, key))
