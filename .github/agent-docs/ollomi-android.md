# Ollomi Android target — fork override

Fork-specific operational detail for the Flutter app (`app/`). The app guide `app/AGENTS.md` keeps only a summary pointer; read this before touching the Ollomi Android target.

The active Android target uses local `AuthService` sessions and a runtime-selected server. Recording can use the phone microphone, a phone call when Android permits it, or an already-connected compatible device; it can also import audio. Firebase, Google/Apple login, PostHog, Intercom, cloud STT SDK setup, and automatic Omi pairing in the upstream code must not be restored for this target. Android IDs are `me.ollomi.app.dev` / `me.ollomi.app`. No Firebase generated options or cloud environment files are required. The general l10n, generated-file and agent-flutter rules still apply.

## Publishing workflow

The Ollomi publishing workflow runs Flutter and native BLE tests on every ref. It compiles and uploads a debug APK on pull requests and `main` pushes, but not on release tags (which build the signed APK instead). Tag APK compilation runs in parallel with tests; `release-publish` requires all tests and artifacts to pass before creating a public release. Both Android jobs use the Gradle setup action in addition to Flutter's SDK cache; do not add a second Gradle cache to the Java setup step.

## Startup, discovery and provenance

The self-hosted Android startup must call `DeviceService.start()` through `ServiceManager.start()` before onboarding or the device picker tries to scan; otherwise discovery silently remains in `init`. BLE classification accepts Omi CV1 and original Friend devkit advertisement names when Android omits their service UUID, while `Friend_` remains the separate LC3 Friend Pendant type. Keep the startup and discovery regression tests in the Ollomi CI list.

The original `Friend` keeps the Omi BLE/audio transport but sends `friend_com` as conversation provenance. The `Friend_…` Pendant sends 30-byte LC3 frames to the server and uses `lc3_fs1030` in native batch filenames; `BatchRecordingInfo` must parse the trailing `_fs160_` field rather than the `_fs1030_` embedded in the codec name. Keep both source-mapping and batch-filename tests in the Ollomi CI list.

## BLE Opus reassembly

Omi CV1 Opus frames can span several BLE notifications: the firmware header has a 16-bit per-notification packet id and an 8-bit fragment index reset to zero at each frame. Foreground Dart and native Android background/batch paths must reassemble contiguous fragments and send/write only complete frames; the next index-zero notification confirms the previous frame. The final unconfirmed frame is dropped at teardown. Keep Dart audio-source and native assembler/streamer regression tests in Ollomi CI.

## Auth scope

`AuthenticatedProductScope` owns `SyncProvider` above `MaterialApp`, not inside its home route: the connected-device page is pushed through the Navigator and needs the same provider. Keep the route-level regression test in the Ollomi CI list. The scope exists only while local authentication is active, so account-specific WAL state is disposed on sign-out.

## Build & test commands

From `app/`: `flutter pub get`, `flutter test --concurrency=2`, and `flutter build apk --debug --flavor dev --target-platform android-arm64,android-x64`. Dart analyze ratchet: `app/scripts/analyze_ratchet.sh`. Self-hosting docs: `docs/OLLomi_SELF_HOSTING.es.md` and `docs/OLLomi_VALIDATION.md`.
