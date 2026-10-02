-- SIGMALYTIC — Add portfolio_value to user_preferences (2026-10-02)
-- ADDED: lets a subscriber record their total account/portfolio value
-- (e.g. $100,000) so the Portfolio tab's "Alloc." column can show what
-- share of the WHOLE account a position represents, instead of what
-- share of currently-deployed capital it represents (which was
-- confusingly always 100% with a single open position).
-- Idempotent -- safe to run more than once.

alter table public.user_preferences
    add column if not exists portfolio_value numeric(18,2);
