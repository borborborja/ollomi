# Ollomi backend

This is the deployed, self-hosted backend for the Ollomi Android fork. The original `backend/main.py` and cloud integrations remain as upstream reference; they are not imported by this service or included in its Docker image.

Use the root `compose.yaml`. See [installation and operation](../../docs/OLLomi_SELF_HOSTING.es.md), [research and design](../../docs/OLLomi_RESEARCH.es.md), and [validation](../../docs/OLLomi_VALIDATION.md).

## Components

- `main.py`, `config.py`: startup, capability discovery, configuration.
- `db.py`, `migrations/`: PostgreSQL records, sessions, durable jobs/events, pgvector. Migrations are required before startup.
- `security.py`, `admin.py`, `profiles.py`: local Argon2 passwords, short-lived access JWTs, rotating refresh tokens, administrator-managed inference profiles and encrypted credentials.
- `audio.py`, `sync.py`, `worker.py`: bounded uploads, framed Omi WAL/Opus decoding, live WebSocket capture, durable processing and lease fencing. Audio retries retain originals. Recording parts are serialized per conversation.
- `records.py`, `mobile.py`, `playback.py`: owner-scoped Omi mobile contracts, signed playback URLs bound to a live session, export and deletion.
- `search.py`, `chat.py`: owner-scoped vector/text retrieval and streamed chat. Embedding generations isolate incompatible models; changes queue reindexing.
- `integrations.py`: explicit exports to local WebDAV, CalDAV VTODO, webhooks; explicit MCP Streamable HTTP tool discovery/calls. Administrator credentials are never returned.
- `tts.py`, `firmware.py`: local Piper synthesis and operator-provisioned firmware.

## Development

Python 3.11. Install `requirements.txt` and `requirements-test.txt` in an isolated environment. Run `PYTHONPATH=backend pytest backend/selfhost/tests -q` from the repository root. Unit tests use SQLite and mock the Redis login limiter; they do not replace the real PostgreSQL/inference smoke test.

`docker compose -f compose.yaml -f deploy/compose.dev.yaml up -d` mounts the source for development. Restart changed Python services. Production uses the image without this override.

Data modifications and durable work admission share a PostgreSQL transaction. Celery/Redis messages are delivery hints; the scheduler recovers queued jobs and expired leases. A failed provider call marks the job failed; explicit retry is available through `/v1/import/jobs/{id}/retry`. Completed transcripts survive a later summary failure. Provider credentials are encrypted with a key derived from `OLLOMI_SECRET_KEY`; preserve this secret together with the database backup.

The API currently supports the core mobile contracts, not every commercial/cloud endpoint in upstream Omi. Exact limitations are listed in the validation document.
