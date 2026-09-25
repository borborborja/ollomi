# sdks/ — Agent Guide

Component guide for `sdks/`. General engineering rules: root `AGENTS.md`.
Client SDKs for the Omi device and backend. The device protocol is polyglot —
the same BLE/wire contract is implemented in five languages under `device/`.

## Sub-SDKs

| Path | Language | What it is |
|---|---|---|
| `device/` | cpp / dart / go / rust / typescript | Portable device BLE protocol helpers |
| `python/` | Python | Desktop SDK — bleak scan, Opus decode, Deepgram/Whisper STT |
| `python-cli/` | Python | `omi` CLI — memories, conversations, goals from the terminal |
| `react-native/` | TypeScript | React Native SDK — `react-native-ble-plx` transport |
| `rust/` | Rust | `omi-device` crate — protocol helpers + optional STT features |
| `swift/` | Swift | iOS/macOS library; exposed via root `Package.swift` as `omi-lib` |

## Build & Test

| SDK | Build | Test |
|---|---|---|
| `device/go` | — | `go -C sdks/device/go test -race ./...` (manifest: `go-device-sdk-tests`) |
| `device/typescript` | — | `bun test sdks/device/typescript` (manifest: `typescript-device-sdk-tests`) |
| `device/cpp` | `cmake -DOMI_DEVICE_BUILD_TESTS=ON -B build && cmake --build build` | `ctest --test-dir build` |
| `device/dart` | — | `flutter test` (in `sdks/device/dart/`) |
| `device/rust` | — | `cargo test` (in `sdks/device/rust/`) |
| `python/` | `pip install -e .[dev]` | `pytest` (in `sdks/python/`) |
| `python-cli/` | `pip install -e .[dev]` | `pytest` (in `sdks/python-cli/`) |
| `react-native/` | `npm run build` (react-native-builder-bob) | `npm test` (jest), `npm run typecheck` |
| `rust/` | — | `cargo test` (in `sdks/rust/omi-device/`) |
| `swift/` | `swift build` (at repo root — root `Package.swift`) | — |

## Conventions

- **Device protocol parity.** `device/PROTOCOL.md` and `device/PARITY.md` define
  the wire contract; every language port must satisfy the same fixtures.
- **BLE is injected, not bundled.** `device/cpp/` removed its SimpleBLE
  dependency (BUSL-1.1); consumers implement `omi::device::BleBackend` against
  their platform stack. Go uses `-tags ble` with tinygo bluetooth.
- **Swift is repo-root.** `sdks/swift/Sources/` is compiled by the root
  `Package.swift` (`omi-lib` target), not a local `Package.swift`.
- **Python toolchain.** Both Python SDKs use `pyproject.toml` with setuptools;
  dev extras pull pytest, black, isort, mypy. Format: root `AGENTS.md` rules.
- **React Native.** `react-native-ble-plx` peer dep; jest config is
  `jest.config.issue12979.js`, not the default.
