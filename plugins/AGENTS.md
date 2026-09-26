# plugins/ — Agent Guide

Component guide for `plugins/`. General engineering rules: root `AGENTS.md`.

## Overview

`plugins/` is a Python monorepo of integration plugins for Omi: a shared SDK
(`omi-plugin-sdk/`), 29 independently deployed `omi-*-app/` services, and a
legacy monolith kept only because a deploy target still builds it. Active
refactoring tracked in `LEGACY_MONOLITH.md` and `PLUGIN_REFACTOR_AUDIT.md`.
## Layout

- `omi-plugin-sdk/` — models-only Python package (`omi_plugin_sdk.models`:
  `Conversation`, `TranscriptSegment`, `ActionItem`). Monolith installs via
  `plugins/requirements.txt`; each `omi-*-app/` pins `../omi-plugin-sdk`.
- `omi-*-app/` (29 dirs) — self-contained FastAPI services: `main.py`,
  `requirements.txt`, `Procfile` / `railway.toml`, optional `test_main.py`,
  optional `db.py` / `models.py`.
- `main.py`, `db.py`, `models.py`, `utils.py` — legacy monolith root.
  `models.py` is a compatibility shim over `omi_plugin_sdk.models`.
- `Dockerfile`, `Dockerfile.datadog` — monolith image builds.
- `basic/`, `oauth/`, `zapier/`, `chatgpt/`, `subscription/`,
  `notifications/`, `iq_rating/`, `_multion/` — monolith routers.
- `templates/` — setup-flow HTML. `scripts/check_plugin_imports.py` —
  imports every `omi-*-app/main.py` and builds OpenAPI schemas.
- `instructions/` — per-app instruction/asset content. `hume-ai/`,
  `composio/`, `uber_call/` — standalone services. `logos/`, `import/` —
  static assets.
## Adding / changing a plugin

- New integrations go in a new `omi-<name>-app/` directory, not the monolith.
- Each app owns its `main.py`, `requirements.txt`, and deploy descriptor.
- Pin the SDK as `../omi-plugin-sdk` in the app's `requirements.txt`; do not
  add it to `plugins/requirements.txt`. Do not add new business logic to
  `plugins/main.py` or `plugins/_multion/`.
- If the app imports SDK models, re-export from a local `models.py` rather
  than duplicating `Structured` / `ActionItem` definitions.
## Testing

- Four plugin test files are registered as checks in
  `.github/checks-manifest.yaml` and must keep running:
  `plugins/omi-hacker-news-app/test_main.py`,
  `plugins/omi-usgs-earthquake-app/test_main.py`,
  `plugins/omi-notion-app/test_main.py`,
  `plugins/omi-slack-app/test_slack_search.py`.
- Run an app's tests from its own directory; apps without tests have none.
- `scripts/check_plugin_imports.py` is the cross-app import contract check.
## Gotchas

- The monolith deploy target blocks deletion of `plugins/main.py`,
  `plugins/Dockerfile`, and `plugins/_multion/` — see `LEGACY_MONOLITH.md`.
- `backend/models/structured.py` keeps a fallback when `omi_plugin_sdk` is
  absent (backend images copy only `backend/`); full-repo runs use the SDK.
- Railway/Nixpacks apps use `../omi-plugin-sdk`; builds with an isolated
  root excluding siblings will fail dependency install.
- `plugins/_mem0` and `plugins/advanced/` were deleted in 2026.
