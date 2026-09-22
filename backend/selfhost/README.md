# Ollomi backend

This is the deployed, self-hosted backend for the Ollomi Android fork. The original `backend/main.py` and cloud integrations remain as upstream reference; they are not imported by this service or included in its Docker image.

Use the root `compose.yaml`. See [installation and operation](../../docs/OLLomi_SELF_HOSTING.es.md), [research and design](../../docs/OLLomi_RESEARCH.es.md), and [validation](../../docs/OLLomi_VALIDATION.md).

## Components

- `main.py`, `config.py`: startup, capability discovery, configuration.
- `db.py`, `migrations/`: PostgreSQL records, sessions, durable jobs/events, pgvector. Migrations are required before startup.
- `security.py`, `accounts.py`, `admin.py`, `profiles.py`: local Argon2 passwords, idempotent administrator bootstrap, short-lived access JWTs, rotating refresh tokens, administrator-managed inference profiles and encrypted credentials.
- `audio.py`, `sync.py`, `worker.py`: bounded uploads, framed Omi WAL/Opus decoding, live WebSocket capture, durable processing and lease fencing. Audio retries retain originals. Recording parts are serialized per conversation.
- `extraction.py`: conservative validation of model-produced summaries, commitments, dated events, decisions, goals, people and memories. Dates without a timezone remain text and never become automatic reminders.
- `records.py`, `mobile.py`, `playback.py`: owner-scoped Omi mobile contracts, signed playback URLs bound to a live session, export and deletion.

Transcript segments use cumulative audio-part offsets in `file_ids` order. Mobile conversation responses expose `audio_files` in that order even after a part is retried; the Android playlist can therefore seek to a segment and stop at its end without a conversation-level MP3. If any part is unavailable, segment taps fail closed instead of jumping to the wrong recording. The existing `conversation_audio` response remains `null` for this backend.
- `search.py`, `chat.py`: owner-scoped vector/text retrieval and streamed chat. Embedding generations isolate incompatible models; changes queue reindexing.
- `integrations.py`: explicit exports to local WebDAV, CalDAV VTODO, webhooks; explicit MCP Streamable HTTP tool discovery/calls. Administrator credentials are never returned.
- `tts.py`, `firmware.py`: local Piper synthesis and operator-provisioned firmware.
- `knowledge_graph.py`: owner-scoped mind map generated from conversation and memory records; no graph database or extra model.
- `static_map.py`: authenticated OpenStreetMap preview images, with a persistent seven-day tile cache and a configurable tile-server URL.

## Development

Python 3.11. Install `requirements.txt` and `requirements-test.txt` in an isolated environment. Run `PYTHONPATH=backend pytest backend/selfhost/tests -q` from the repository root. Unit tests use SQLite and mock the Redis login limiter; they do not replace the real PostgreSQL/inference smoke test.

`docker compose -f compose.yaml -f deploy/compose.dev.yaml up -d` mounts the source for development. Restart changed Python services. Production uses the image without this override.

Data modifications and durable work admission share a PostgreSQL transaction. Celery/Redis messages are delivery hints; the scheduler recovers queued jobs and expired leases. A failed provider call marks the job failed; explicit retry is available through `/v1/import/jobs/{id}/retry`. Completed transcripts survive a later summary failure. Provider credentials are encrypted with a key derived from `OLLOMI_SECRET_KEY`; preserve this secret together with the database backup.

After each transcript, the selected chat profile returns a structured extraction. Ollomi persists task, memory, goal, decision and calendar-event records with provenance from their source conversation. It stores a deadline only when the model returned an ISO-8601 instant with a timezone; ambiguous wording is retained as `due_text` or `date_text` for review. Events are therefore ready for a future CalDAV `VEVENT` exporter, while the current CalDAV export is deliberately limited to explicit task `VTODO` exports.

Inference can be owned entirely by the host environment. Ordered `OLLOMI_STT1_*`, `OLLOMI_CHAT1_*` and `OLLOMI_EMBEDDING1_*` entries are synchronized as read-only profiles; increasing suffixes are tried as fallbacks. When a purpose has environment profiles, per-user selection and app-side editing are disabled for that purpose. Runtime success/failure state is exposed without URLs or credentials through `/v1/ai-status`.

The local speech and Ollama containers use the Compose profiles `local-whisper` and `local-ollama`. `OLLOMI_SEED_LOCAL_WHISPER` and `OLLOMI_SEED_LOCAL_OLLAMA` control whether matching default database profiles are created. An external-only deployment leaves both false, activates neither Compose profile and must provide numbered STT, chat and embedding profiles before processing audio.

`OLLOMI_ADMIN_EMAIL` and `OLLOMI_ADMIN_PASSWORD` create the initial administrator once during startup. Existing accounts are never modified. The CLI also accepts `create-admin` and `reset-password` with `--password-env NAME` or `--password-stdin`, so automation never needs to expose a password in the process argument list. Remove the bootstrap password from the container environment after the first successful login.

Environment profile hostnames may be temporarily unresolved during startup; the seed logs a warning and continues. URL policy and DNS are checked again immediately before every provider call, so an unavailable or disallowed target still fails closed at use time.

The API currently supports the core mobile contracts, not every commercial/cloud endpoint in upstream Omi. Exact limitations are listed in the validation document.
