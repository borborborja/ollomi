# Ollomi validation record

This file records what was verified for this checkout. It is deliberately not a
claim that every Omi cloud feature, physical device, or third-party model has
been tested.

## Verified locally — 23 September 2026

| Area | Evidence |
| --- | --- |
| Self-hosted backend | `PYTHONPATH=backend python -m pytest backend/selfhost/tests -q -p no:cacheprovider` passed **87 tests**, with two codec tests skipped because this macOS host does not provide the Linux image's native LC3/Opus libraries. Contracts include per-user audio-retention persistence, admission-time snapshots, success-only purge, failed/legacy retention, live status order, bounded preview saturation and complete durable WAV output. |
| Configuration | `docker compose config --quiet` passed for the source, external-API and voiceprint Compose examples with temporary `.env` files. The external example now also validates with TLS disabled and no `OLLOMI_TLS_DOMAIN`; the optional `public-tls` profile refuses to start if an operator has not supplied that domain, before Caddy can bind an HTTP listener. The included proxy persists certificate storage and keeps the plain maintenance proxy on its loopback binding. |
| Fresh external-API stack | An isolated Compose project started PostgreSQL/pgvector, Redis, Typesense, migrations, API, worker and scheduler from the current built backend image. Docker marked the API healthy and `/health/ready` returned `{"status":"ok"}` after PostgreSQL, Redis and Typesense were available. Earlier local checks also covered `/v1/server-info` and password login. Its containers, volumes and temporary configuration were removed after the test. |
| Backup and recovery | An isolated external-API stack ran `scripts/selfhost_backup.sh`: writers stopped, PostgreSQL dump, audio archive, instance configuration and revision record were checksummed successfully; all writers were then restarted. It then deliberately truncated its test records/jobs and removed its test audio. `scripts/selfhost_restore.sh` validated checksums, the instance key and archive paths before writing, restored **2 records** and **1 audio file**, and queued **1** clean derived-index rebuild. Both scripts detect source-stack `api` and published external-stack `ollomi-api` service names. The isolated containers, volumes and temporary configuration were removed after the test. |
| MCP and local OAuth | With MCP enabled in that isolated stack, protected-resource and authorization-server metadata returned the configured HTTPS issuer. A personal MCP key was created, redacted on later listing, and successfully listed four read-only tools. Contracts cover PKCE, one-time code and refresh-token rotation, revocation, client isolation and safe redirect registration. |
| Copyable external/LAN setup | The root `.env.example` selects the connected Compose override without local Whisper/Ollama, starts with MCP disabled, and includes one numbered STT, chat and embedding profile. Replacing its instance secret in an isolated local Compose project started PostgreSQL/pgvector, Redis, Typesense, migration, API, worker, scheduler and proxy; the API became healthy and `/health/ready` returned `{"status":"ok"}`. Local administrator login, compatible `server-info`, and all three environment-managed model purposes were also verified without contacting an inference provider. The temporary containers, networks and volumes were removed. A backend contract and CI smoke gate protect that CPU-first installation path. |
| Provider adapters | Contract tests cover native Gemini, Deepgram and AssemblyAI transcription paths plus Voyage and Cohere embeddings; OpenAI-compatible STT/chat/embedding and ordered environment fallbacks remain covered by the backend suite. |
| Model-selection policy | `OLLOMI_ALLOW_USER_MODEL_SELECTION=false` is the default. The server announces that state in its sanitized AI status, returns `403` for a direct preference write while disabled, and accepts only configured profile IDs when enabled; the Android settings disable the corresponding radios when the server has not authorized selection. |
| Owner voice and speaker turns | The separate CPU-only SpeechBrain ECAPA image built successfully. It pins the reviewed `speechbrain/spkrec-ecapa-voxceleb` revision and SHA-256 values for all three loaded checkpoints at image build time, rewrites its configuration to the baked local model directory, and enables Hugging Face offline mode at runtime. A `--network none --read-only` container with only a temporary writable `/tmp` loaded the baked model and encoded a silent waveform to a 192-dimensional vector: this verifies no runtime model transfer, not recognition quality. Earlier endpoint checks reached health readiness, returned a normalized 192-dimensional embedding and returned a speaker turn from `/v1/diarize` for a temporary WAV sample. Backend contracts verify text-only STT is split over local turns, native provider labels are retained, and a voice-service outage does not fail transcription. No enrollment audio was retained. |
| Android STT routing | The self-hosted capture resolver ignores legacy direct-provider keys and on-device mode stored on the phone, and always selects the authenticated server's `/v4/listen` path. The speech-profile flow has the same invariant: it surfaces server STT exhaustion instead of falling back to an on-device provider. Unit, capture-entry and speech-profile contracts are included in the Android CI gate. |
| Live capture security | A WebSocket without a bearer token is rejected with `4401`; an authenticated PCM16 connection receives its initial state, creates an owner-bound conversation and rejects an unsupported codec with `4400`. The Android CI gate includes the socket header/authentication unit contract. |
| Live capture state and retention | `/v4/listen` reports source-aware `ready`, receipt, transcription, no-speech, delayed and unavailable states while writing the definitive WAV independently of the preview queue. Flutter contracts verify CV1 source/stage mapping, exclusive source changes and all three persistent active-button behaviors. The selected Android workflow suite passed **143 tests** locally. |
| Android Firebase removal | The Android Gradle configuration, ProGuard rules, `pubspec.yaml` and lockfile contain no Firebase, Google Services or Crashlytics dependency/reference. |
| Self-host authority | The app's authenticated HTTP/WebSocket matching uses only the selected Ollomi URL; Omi Parakeet fails closed instead of configuring a direct URL; and the visible device, referral, privacy, developer-key and share defaults no longer point to Omi. The CI gate rejects the former Omi hosts in those core routes and runs their focused unit contracts. |
| Android validation | Flutter 3.44.5 completed `flutter analyze lib --no-fatal-warnings --no-fatal-infos` without errors (the existing source still reports lint warnings/information), the four native BLE endpoint Gradle tests passed, and `assembleDevDebug` produced `app-dev-debug.apk` locally. This does not replace installation and testing on a physical phone and Omi CV1. |
| Payment gating | The self-hosted app always reports no subscription UI, no transcription-credit exhaustion and no payment gate for phone calls. Locked legacy rows and the chat quota handler both check that policy before navigating to a plan sheet. Its retained plans, checkout, upgrade, cancellation and customer-portal provider methods are no-ops; app submission always writes a free app and older paid app metadata is displayed as free. |
| Release safeguards | `.github/workflows/ollomi-release.yml` runs backend contracts, focused local-auth, payment-policy, server-authoritative-STT and WebSocket-auth Flutter tests, and native BLE endpoint tests on every CI run. Pull requests and `main` pushes also compile and upload a complete debug APK; version tags instead compile the signed APK in parallel with validation and publish nothing until every required test and artifact succeeds. The two Android jobs use Flutter and Gradle caches. Pull requests and manual dispatches build (without publishing) backend, speech and CPU voiceprint images; only reviewed `main`/tag pushes authenticate to GHCR and publish the same versioned images. Signed APK generation is limited to `v*` tags, so an initial fork can validate CI before its private signing material exists. It also rejects reintroduction of Firebase/Google Services/Crashlytics into Android. |

## Not yet a production assertion

- No image, APK, Git tag, GitHub release, remote fork or deployment was
  published by this checkout.
- The debug APK compiled locally and the selected Flutter and native Android
  tests passed, but the clean GitHub workflow and signed release build have not
  run because nothing from this checkout has been pushed or tagged.
- No Android device/emulator, Omi/Friend hardware, real model account, real
  voice enrollment, production TLS proxy, long recording,
  offline recovery or soak test was executed in this revision.
- Voiceprint distinguishes the enrolled owner only when the optional service is
  configured. The ECAPA energy-clustering fallback provides provisional local
  speaker turns for text-only STT; it has not been quality-evaluated on a real
  multilingual conversation. Provider labels and any provisional label are not
  a guarantee of identity; threshold and speaker-turn quality must be
  calibrated with authorised recordings.

## Required release gates

1. Commit the reviewed changes and let the GitHub workflow complete both test
   jobs, including the external/LAN Compose smoke gate, the native BLE tests
   and the complete debug Android build on its clean Linux runner. Then create
   a `v*` release tag and require the signed Android build to pass too.
2. Install the resulting APK on a physical Android phone; test first-run server
   selection, password login, model selection, audio upload and reconnect.
3. Pair the available Omi and Friend hardware separately, including an
   interrupted transfer and a background/restart cycle.
4. Deploy the external-API Compose example to the target Linux x86-64 server
   with a real `.env`, HTTPS reverse proxy and backups; run the smoke test using
   a dedicated account.
5. If owner recognition is enabled, deploy the voiceprint service on the model
   server, enroll a consented sample, and evaluate false matches/misses before
   treating the threshold as a production default.
6. Exercise the MCP OAuth flow with the intended real client through the final
   HTTPS URL, then verify token/key revocation.

Do not describe a release as stable until every applicable gate has recorded
evidence. The local commands are:

```sh
docker build -f deploy/Dockerfile -t ollomi-backend:local .
docker run --rm -v "$PWD:/work:ro" -w /work \
  -e OLLOMI_SECRET_KEY=replace-with-a-test-only-32-character-secret \
  ollomi-backend:local sh -ec \
  'pip install --user pytest==8.3.5 pytest-asyncio==0.26.0 respx==0.22.0 && PYTHONPATH=backend python -m pytest backend/selfhost/tests -q -p no:cacheprovider'
cd app && flutter pub get && flutter test \
  test/unit/local_auth_test.dart test/unit/env_test.dart \
  test/unit/selfhost_payment_policy_test.dart \
  test/unit/stt_mode_resolver_test.dart test/unit/pure_socket_auth_test.dart \
  test/unit/account_cutover_gate_test.dart test/unit/share_links_test.dart \
  test/unit/multipart_401_retry_test.dart test/unit/transient_network_error_test.dart \
  test/widgets/connect_device_get_omi_test.dart \
  test/services/capture/stt_mode_capture_entry_test.dart \
  test/providers/speech_profile_provider_test.dart
cd android && ./gradlew :app:testDevDebugUnitTest \
  --tests 'com.friend.ios.batch.NativeBleServerEndpointPolicyTest' \
  --tests 'com.friend.ios.batch.OmiBackgroundAudioStreamerTest' \
  --tests 'com.friend.ios.batch.NativeBleGeolocationHeaderTest' --no-daemon
```
