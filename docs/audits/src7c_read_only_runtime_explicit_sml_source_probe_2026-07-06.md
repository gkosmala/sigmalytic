# SRC7C - Read-Only Runtime Explicit SML Source Probe

SRC7C adds a deployed read-only endpoint:

`/api/campaign/src7c-read-only-runtime-explicit-sml-source-probe`

## Purpose

SRC7A created the explicit SML / structural-location contract.

SRC7B created the read-only runtime adapter design.

SRC7C exposes a deployed read-only probe for that adapter.

## Strict Boundary

SRC7C is read-only.

SRC7C does not persist records.
SRC7C does not write to Supabase.
SRC7C does not mutate campaigns.
SRC7C does not execute D3D.
SRC7C does not authorize D3D.
SRC7C does not confirm operator control.
SRC7C does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Expected Result

In fixture mode, SRC7C should prove that the deployed SRC7B adapter validates explicit SML records and rejects invalid proxy records.

In runtime mode, SRC7C may return no records until an explicit SML source is supplied.

D3D remains blocked.
