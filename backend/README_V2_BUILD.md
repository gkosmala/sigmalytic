# Sigmalytic V2

Core V2 objective:

Find, score, rank, and monitor institutional/operator campaigns using:

- Wyckoff
- David Weis
- Jesse Livermore
- Operator Dominance
- Campaign lifecycle intelligence
- Fractal alignment
- Signal fusion

Portfolio construction remains an add-on layer after campaign intelligence is complete.

## Backend

Run locally:

```bash
uvicorn backend.main:app --reload
```

## Health

```text
GET /health
GET /api/v2/intelligence/health
GET /api/v2/dashboard/health
GET /api/v2/operator-dominance/health
```
