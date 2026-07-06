# D4F.1 - Runtime Import Repair

D4F.1 is a narrow runtime repair for the D4F live read-only HVN/POC construction endpoint.

## Purpose

D4F introduced a deployed read-only HVN/POC construction endpoint.

The endpoint construction logic uses Python math functions for finite-number validation and profile construction. D4F.1 ensures the deployed backend module has the required `math` import before live probing.

## Strict Boundary

D4F.1 does not persist bars.
D4F.1 does not write to Supabase.
D4F.1 does not mutate campaigns.
D4F.1 does not execute D3D.
D4F.1 does not authorize D3D.
D4F.1 does not confirm operator control.
D4F.1 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

D4F.1 is a runtime repair only.
