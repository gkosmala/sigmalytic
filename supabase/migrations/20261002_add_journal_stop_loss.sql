-- SIGMALYTIC — Add stop_loss to trade_journal (2026-10-02)
-- ADDED: user-requested ability to record a stop loss per journal
-- entry, alongside the new PATCH /api/journal/entry/{id} edit
-- endpoint (backend/trade_journal_api.py, backend/trade_journal_service.py).
-- Idempotent -- safe to run more than once.

alter table public.trade_journal
    add column if not exists stop_loss numeric(18,6);
