# backend/selfhost — Agent Guide

Component guide for `backend/selfhost/`. General engineering rules: root `AGENTS.md`.

## Overview

Deployed backend for the Ollomi fork. Self-contained FastAPI app with PostgreSQL/pgvector, SQLite-backed unit tests, static admin UI, and Celery worker/scheduler. Upstream `backend/main.py` and cloud/GKE workflows are reference-only; this is the only runtime the fork deploys via `.github/workflows/ollomi-release.yml`.

## Entry points & run/test

- **API**: `backend/selfhost/main.py` — FastAPI app, mounts routers and `admin_ui/` static files.
- **Worker/scheduler**: `backend/selfhost/worker.py` — Celery app with beat schedule (recover, retention, reminders).
- **CLI**: `backend/selfhost/cli.py` — `create-admin`, `reset-password`, Alembic migration helpers.
- **Migrations**: `backend/selfhost/migrations/` (Alembic) — run at API startup before serving requests.
- **Test command**: `PYTHONPATH=backend pytest backend/selfhost/tests -q` from the repository root. Unit tests use SQLite and mock Redis; they do not replace PostgreSQL/inference smoke.
- **Dev compose**: `docker compose -f compose.yaml -f deploy/compose.dev.yaml up -d` mounts source; production uses the image without this override.

## Layout

- `main.py`, `config.py` — startup, capability discovery, settings.
- `db.py`, `migrations/` — PostgreSQL records, sessions, durable jobs/events, pgvector.
- `security.py`, `accounts.py`, `admin.py`, `profiles.py` — Argon2 passwords, JWTs, admin-managed inference profiles, encrypted credentials.
- `audio.py`, `sync.py`, `worker.py` — uploads, WAL/Opus/LC3 decoding, live WebSocket capture, durable processing, lease fencing.
- `extraction.py` — validation of model-produced summaries, commitments, events, decisions, goals, people, memories.
- `records.py`, `mobile.py`, `playback.py` — owner-scoped mobile contracts, signed playback URLs, export/deletion.
- `search.py`, `chat.py` — vector/text retrieval, streamed chat.
- `integrations.py` — WebDAV, CalDAV VTODO, webhooks, MCP Streamable HTTP.
- `tts.py`, `firmware.py` — Piper synthesis, operator-provisioned firmware.
- `knowledge_graph.py` — owner-scoped mind map from conversation/memory records.
- `static_map.py` — authenticated OpenStreetMap previews, seven-day tile cache.
- `admin_ui/` — static HTML/CSS/JS admin dashboard.
- `tests/` — 15 test files covering API, audio contracts, extraction, integrations, MCP, profiles, provider adapters, recovery, voiceprint.

## Conventions/Gotchas

- **Dependencies**: edit `selfhost/requirements.in` (runtime) or `selfhost/requirements-test.in` (test), then `uv pip compile` to regenerate the corresponding `.txt`. Speech service has its own lock in `services/speech`.
- **Migrations run at startup**: the API container applies Alembic migrations before serving requests; worker and scheduler wait for API health.
- **Secrets/data outside Git**: `OLLOMI_SECRET_KEY` encrypts provider credentials; preserve it with database backups. Local secrets and data never committed.
- **Python 3.11 only**: Dockerfile pins 3.11; no 3.12+ syntax.
- **Unit tests use SQLite**: they mock the Redis login limiter and do not require PostgreSQL; they are not a substitute for the real database smoke test.
- **Admin bootstrap**: `OLLOMI_ADMIN_EMAIL` and `OLLOMI_ADMIN_PASSWORD` create the initial administrator once at startup; remove the bootstrap password from the container environment after first login.
- **Inference profiles**: ordered `OLLOMI_STT1_*`, `OLLOMI_CHAT1_*`, `OLLOMI_EMBEDDING1_*` env entries are synchronized as read-only profiles; increasing suffixes are fallbacks.
- **Audio retention**: `GET/POST /v1/users/private-cloud-sync` controls global audio retention; default `false` queues deletion after successful processing.

See `backend/selfhost/README.md` for component detail and `docs/OLLomi_SELF_HOSTING.es.md` for installation, models, Android, and backups.
