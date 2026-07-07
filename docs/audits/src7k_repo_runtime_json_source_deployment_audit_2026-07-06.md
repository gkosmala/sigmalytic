# SRC7K - Repo Runtime JSON Source Deployment Audit

SRC7K commits the validated SPY explicit structural-location JSON source into the repository as a read-only runtime source.

## Option A

The source file is committed into the repo at:

`runtime_sources/explicit_sml_runtime_source.json`

## Boundary

SRC7K does not execute D3D.
SRC7K does not authorize D3D.
SRC7K does not mutate Supabase.
SRC7K does not mutate campaigns.
SRC7K does not confirm operator control.
SRC7K does not create a trade signal.

## Purpose

SRC7K allows the deployed backend to read the explicit SML JSON source from the repo filesystem.

## Live Probe

After deployment, probe SRC7G with:

`/api/campaign/src7g-runtime-dry-run-preflight-endpoint?symbols=SPY&fixture_mode=none&json_file_path=runtime_sources/explicit_sml_runtime_source.json`

Expected result:

- source-only dry-run readiness may pass;
- production D3D eligibility remains false;
- D3D execution remains unauthorized;
- operator control remains unconfirmed;
- recommendation remains DO_NOT_EXECUTE_D3D.

D3D remains blocked.
