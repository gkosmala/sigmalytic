# D3V — D3D Dry-Run Candidate Preflight Audit

## Purpose

D3V creates a read-only dry-run candidate preflight endpoint for future D3D review.

## Doctrine Boundary

D3V does not execute D3D.
D3V does not authorize D3D.
D3V does not mutate campaigns.
D3V does not confirm operator control.

## Preconditions Checked

D3V checks whether candidate rows satisfy the D3U protocol boundary:

- candidate exists in D3C.2T stealth monitoring
- complete doctrine-leg evidence exists
- explicit geometry SML exists
- inferred SML is rejected
- `HVN_ABSORPTION_PROXY` is rejected as true HVN/POC
- true HVN/POC source is required
- D3D production confirmation is not already present

## Guardrails

D3V:

- remains dry-run
- does not write to Supabase
- does not mutate campaigns
- does not confirm operator control
- does not unconfirm operator control
- does not execute production D3D
- does not use D3D as a production source
- does not affect score
- does not affect rank
- does not affect campaign state
- does not affect transitions
- does not affect gamma/options
- does not create trade signals

## Expected Initial Result

Because D3C.2R found no true HVN/POC source and D3C.2S showed the high-priority SML evidence is inferred, D3V is expected to produce zero D3D-preflight-eligible candidates.

## No-Drift Statement

D3V is a dry-run preflight review only. Even an eligible row would remain unmutated and unconfirmed unless a future D3D execution protocol is separately authorized.
