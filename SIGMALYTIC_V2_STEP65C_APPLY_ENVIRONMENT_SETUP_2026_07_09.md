# Sigmalytic V2 - Step 65C Apply Environment Setup

Step 65B did not apply the migration.

Required before re-running Step 65B:

1. Install PostgreSQL client tools so psql is available.
2. Set SUPABASE_DB_URL locally in PowerShell.
3. Do not paste the real database URL into ChatGPT.

Example format only:

$env:SUPABASE_DB_URL = "postgresql://postgres:<PASSWORD>@<HOST>:5432/postgres"

Boundary:

- No DB call occurred.
- No migration was applied.
- No Supabase write occurred.
- campaign_pipeline_validated remains false.
- Billing remains blocked.
