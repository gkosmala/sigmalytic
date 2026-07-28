# _archive

Files moved here on 2026-07-28 during a cleanup pass. Nothing in this
folder is imported or run by the live app (confirmed before moving —
render.yaml, backend/main.py, and frontend/app.py were all checked for
references first). Moved with `git mv`, so full history for every file
is preserved; nothing was deleted.

- **frontend_duplicates/** — earlier snapshots of the frontend app
  (`app_github.py`, `app_v2_FINAL.py`, `sigmalytic_app_LATEST.py`,
  `sigmalytic_app_TODAY.py`). The one real, live frontend is
  `frontend/app.py` — that's the only one Render actually starts.

- **root_audit_scripts/** — one-off numbered investigation/repair
  scripts (e.g. `27_route_topology_preflight.py`) generated during past
  debugging sessions. Each did a specific one-time check or fix and
  isn't meant to run again.

- **root_audit_json/** — the JSON output/reports those scripts produced.

- **root_patch_scripts/** — one-off `patch_*.py` scripts that applied a
  specific change to a file (e.g. `patch_logo.py`, `patch_radar_bias_colors.py`)
  and already did their job.

If you ever need to see what one of these used to do, it's all still
here with full git history — nothing is lost, just out of the way.
