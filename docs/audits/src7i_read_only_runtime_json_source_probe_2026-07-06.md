# SRC7I - Read-Only Runtime JSON Source Probe

SRC7I probes the read-only JSON source path selected in SRC7H.

## Context

SRC7H selected:

`READ_ONLY_EXPLICIT_SML_JSON_SOURCE_FIRST`

The SRC7B adapter already supports this source through:

`SIGMALYTIC_EXPLICIT_SML_JSON_PATH`

## Purpose

SRC7I proves that a JSON file containing SRC7A-compliant explicit SML records can be loaded read-only by the SRC7B adapter and passed through the SRC7F no-drift dry-run eligibility review.

## Important Boundary

SRC7I uses temporary fixture JSON only.

The temporary fixture JSON is not runtime production evidence.

SRC7I does not create or commit a real production runtime evidence file.

## Strict Boundary

SRC7I is read-only and dry-run only.

SRC7I does not persist records.
SRC7I does not write to Supabase.
SRC7I does not mutate campaigns.
SRC7I does not execute D3D.
SRC7I does not authorize D3D.
SRC7I does not confirm operator control.
SRC7I does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Expected Result

SRC7I must prove:

- valid explicit SML JSON can load through the read-only adapter;
- proxy / HVN_ABSORPTION_PROXY JSON is rejected;
- mixed JSON validates only the valid records and rejects invalid proxy records;
- missing JSON does not create evidence;
- source-only dry-run readiness can pass from JSON;
- production D3D eligibility remains false.

## Next Step

Proceed to SRC7J runtime JSON source deployment guide.

D3D remains blocked.
