# SRC7J - Runtime JSON Source Deployment Guide Audit

SRC7J creates and audits the runtime JSON source deployment guide.

## Context

SRC7I proved that the read-only JSON source path works with temporary fixture JSON.

That fixture did not create runtime production evidence.

## Purpose

SRC7J documents the exact runtime deployment path for real explicit SML / structural-location records.

## Strict Boundary

SRC7J is documentation and audit only.

SRC7J does not create runtime evidence.
SRC7J does not persist records.
SRC7J does not write to Supabase.
SRC7J does not mutate campaigns.
SRC7J does not execute D3D.
SRC7J does not authorize D3D.
SRC7J does not confirm operator control.
SRC7J does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Required Runtime Configuration

The deployed environment must provide:

`SIGMALYTIC_EXPLICIT_SML_JSON_PATH`

That path must point to a real read-only explicit SML JSON source.

## Next Step

Configure a real runtime JSON source and then proceed to SRC7K runtime environment readiness probe.

D3D remains blocked.
