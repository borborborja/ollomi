# Ollomi validation record

Implementation based on Omi `e02339f4c720eb726fb4b798991b306c817630c5`, branch `ollomi/self-hosted`. Validation performed on Linux x86_64, CPU inference, Python 3.11, Flutter 3.44.5, Dart 3.12.2, Java 21, Android NDK 29.0.14206865. This records observed results, not a claim of full upstream feature parity.

## Completed checks

| Check | Evidence |
|---|---|
| Backend unit/API contracts | 18 tests pass: auth rotation/revocation, ownership, provider-secret redaction, audio acceptance/cancellation, idempotent recording parts, playback ticket binding, malformed WAL rejection, local exports, MCP session protocol and persisted mobile onboarding/language isolation |
| Static Python errors | Ruff E9/F checks pass |
| Android analyzer ratchet | Passes without increasing the warning/info baseline |
| Android build | Debug APK compiled for ARM64 and x86_64; artifact `artifacts/ollomi-dev.apk` with SHA-256 in `artifacts/SHA256SUMS` |
| Real MP3 pipeline | Whisper `tiny` produced a transcript, Ollama `qwen3:0.6b` produced a summary, pgvector and Typesense found the conversation, authenticated playback returned 22,041 bytes, and Ollama streamed a completed chat reply |
| Real embeddings | `embeddinggemma` validated and indexed data in PostgreSQL/pgvector |
| Backup and database restore | Backup script completed; its dump restored into a separate temporary PostgreSQL database with 9 records. That verification database was removed afterwards |

The real input was synthetic speech about sending a project proposal and meeting on Friday. No personal recordings were used. The compact model is an infrastructure test, not a quality benchmark. Initial concurrent Android compilation caused an inference timeout; the job remained failed/retryable with its original retained. The successful run was repeated with sufficient resources.

The first complete inherited Android test run executed 1,863 tests: 1,834 passed and 29 failed. Failures involved removed cloud environment assumptions, disabled analytics dispatch in tests, and missing share-sheet anchors. Those paths were corrected; affected tests were rerun. The final complete run passed all 1,843 tests in 8m42s. After the final control-color and store-prompt adjustments, the analyzer ratchet passed and all 8 focused auth/environment/reauthentication tests passed.

## Android and final runtime evidence

Android API 35 x86_64 emulator, actual local HTTP backend, inspected with agent-flutter/Marionette:

- Entered a custom backend URL and signed in with a local account.
- Saved the primary language and completed onboarding while denying optional background, notification and location permissions. Removed cloud enrollment/knowledge-graph steps and upstream store-review prompts from this flow.
- Inspected AI-profile selection, accounts and the integration editor. The integration editor was inspected during an API restart; its failed initial list load is visible in that screenshot. The production endpoint was subsequently verified directly. No live third-party integration is claimed.
- Selected a synthetic MP3 in Android's Downloads picker, retained its pending copy, uploaded it, observed the durable job finish, and opened its transcript-derived summary in the conversation detail page.
- Evidence: `artifacts/android-profiles.png`, `android-accounts.png`, `android-integration-editor.png`, `android-import.png`, `android-conversation.png`.

Real Piper synthesis returned 9,240 MP3 bytes. Docker network inspection showed API, worker, STT and Ollama attached only to the internal private network; an API outbound Internet connection attempt failed as intended. API/worker/scheduler were recreated from images with no development source bind mounts after the final compatibility endpoints were added.

The final APK rebuild completed in 372.7 seconds; its SHA-256 is recorded in `artifacts/SHA256SUMS`. The temporary emulator was deleted, the RAM build mount was unmounted, and normal build/Gradle cache directories were restored. All nine runtime services are up. The three handoff AI profiles each passed a real provider validation (HTTP 200) after the final restart. An initial private backup is in `artifacts/backup-initial`; all four checksums pass.

The handoff administrator was created with a random password in a mode-600 local file; default profiles point to installed `tiny`, `qwen3:0.6b`, and `embeddinggemma` models. The synthetic test account and its temporary profiles are disabled. Its sample data remains isolated in that disabled account.

## Scope and limitations

- Core local app flows have implementations: conversations/transcripts recorded with the phone, summaries, tasks, memories, folders/people records, search/chat, MP3 import, local identity and AI-profile administration.
- The Android product deliberately has no Omi/Bluetooth pairing, battery, firmware, or device-sync flow. The manifest removes Bluetooth and Companion Device permissions, and the Android activity no longer registers the BLE bridge. Preserved upstream device code is outside the reachable product and is not a supported feature.
- Community-1 weights were not obtained behind the user's account/terms gate. Optional diarization code is present; persistent cross-conversation biometric identification is not implemented or validated. Segment/person assignment is available.
- CUDA configuration is supplied but was not executed on a GPU.
- Local notifications poll durable events while the app can run; there is no Firebase push or guarantee of delivery after Android kills the process.
- CalDAV is explicit VTODO export, not a bidirectional calendar sync. MCP is explicit Streamable HTTP discovery/calls, not autonomous tool execution from chat. These protocol tests use local mocks, not the user's live services.
- Local firmware serving uses operator-provided manifests and hashes; no firmware is downloaded or flashed automatically. Maps launch an installed map app; a self-hosted tile server is not included.
- The commercial marketplace, billing, cloud calls, public sharing, and every evolving upstream memory-ledger/knowledge-graph endpoint are not reproduced. Unsupported upstream cloud endpoints are not redirected to Omi. Core deployment does not import the original cloud backend.
- iOS/macOS packaging and release signing are outside the tested target. The supplied APK is a debug development build.

## Reproduce

```bash
PYTHONPATH=backend pytest backend/selfhost/tests -q
ruff check backend/selfhost services/speech --select E9,F
cd app
flutter test --concurrency=2
bash scripts/analyze_ratchet.sh
flutter build apk --debug --flavor dev --target-platform android-arm64,android-x64
```

Use `scripts/selfhost_smoke.py` with a dedicated local account and a representative audio file for a real-provider test. It creates data in that account. For operational setup, model installation and restore commands see [the operator guide](OLLomi_SELF_HOSTING.es.md).

The retired Firebase/Google collision, Firebase startup and direct-cloud-STT settings tests tested APIs intentionally removed from this fork. Local auth and environment tests replace those assumptions; the analyzer does not hide missing-package errors or introduce broad exclusions.
