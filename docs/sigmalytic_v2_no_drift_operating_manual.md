# Sigmalytic V2 No-Drift Operating Manual

## Architecture

The active live frontend surface is `frontend/sigmalytic_app_TODAY.py`.

The active live surface is Dash. The active live surface is not `frontend/app.py` unless Render's frontend start command is deliberately changed and verified.

Current protected frontend rule:

- Preserve `html.Main(id="main-content")`.
- Preserve the working Dash shell.
- Do not mount diagnostic or lifecycle panels globally above or around `main-content`.
- Do not place D3E/D3F panels in the initial Dash shell.
- Do not run backend GET calls during initial layout construction.

Safe architecture:

    Render Frontend Service
      -> frontend/sigmalytic_app_TODAY.py
      -> Dash shell
      -> html.Main(id="main-content")
      -> callback-rendered tabs

## Doctrine

Operator control is evidence, not a score.

Operator control SHALL NOT be derived from:

- composite score
- campaign score
- survival score
- rank
- tier
- probability
- edge
- expected return
- gamma/options overlay
- historical returns
- future returns
- target hits
- trade signals

Composite Operator Control requires:

1. tested supply exhaustion
2. active demand/support validation
3. structurally meaningful location
4. absence of contrary failure

D3D remains blocked.

No lifecycle, alert, frontend panel, score, rank, probability, gamma overlay, or outcome can authorize D3D.

## Deployment

Deployment target: Render.

Required deployment protocol:

1. Run local syntax checks.
2. Run browser smoke test.
3. Run no-drift regression sweep.
4. Confirm live frontend layout.
5. Confirm live backend D3E.9 clean endpoint.
6. Deploy only after the local checks pass.
7. After deploy, run post-deploy verification.
8. Use clear build cache only when deployment cache contamination is suspected.
9. Preserve rollback tag before high-risk changes.

## Regression

Regression protocol must include:

- smoke test
- no-drift sweep
- buttons test
- Dash layout check
- Dash dependencies check
- forbidden global panel marker check
- D3E.9 backend clean check

Buttons that must remain interactive:

- Command Center
- Live Feed
- Radar Screen
- Scoreboard
- Preferences
- Setup
- Load Symbol

Forbidden global panel markers:

- `d3f1b-today-entrypoint-controlled-persistence-mount`
- `Controlled Persistence Lifecycle`
- `D3F1B_TODAY_FRONTEND_FETCH_ERROR`
- `ATTENTION`

## Rollback

Current rollback / preservation checkpoint:

- Commit: `f431a61`
- Stable tag: `stable-v2-d3f1b-live-ui-unfreeze-remove-global-panel-mount-read-only-2026-07-08`

Rollback rule:

If a future frontend patch freezes buttons or tiles, restore the `f431a61` behavior by removing any global D3E/D3F panel mount from the initial Dash shell.

Do not reintroduce a global D3E/D3F panel mount.

## Status Center

D3F.2 may only be callback-safe.

Allowed future location:

- existing Status Center tab
- Admin diagnostic tab
- callback-rendered diagnostic section
- user-selected tab branch

Forbidden location:

- global initial Dash shell
- above `html.Main(id="main-content")`
- around `html.Main(id="main-content")`

## Operator-Control Evidence

Operator-control evidence must remain separate from score logic.

Required evidence categories:

- tested supply exhaustion evidence
- active demand validation evidence
- support validation evidence
- structural location evidence
- absence of contrary failure evidence

Scores may remain as diagnostics only.

Scores cannot confirm operator control.

Scores cannot authorize D3D.

Scores cannot mutate campaigns.

## Lifecycle Law

Lifecycle transition law is governed by `lifecycle_transition_law.json`.

Every transition requires written evidence law and audit explanation.

No transition may mutate campaigns until D3D production mutation law is separately authored, audited, authorized, and implemented.

## Alerts

Alerts are diagnostic and read-only.

Alerts cannot:

- mutate campaigns
- confirm operator control
- authorize D3D
- create trade signals
- touch Stripe

## Stripe / Billing

Stripe and billing remain last.

Stripe cannot be advanced until:

- live UI is stable
- regression suite passes
- campaign pipeline is validated
- operator-control evidence doctrine is protected
- alerts remain read-only
- documentation is complete

Alert guardrail exact phrase: alerts cannot create trade signals.
