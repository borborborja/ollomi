# desktop/context-for-claude — Agent Guide

Component guide for `desktop/context-for-claude/`. General engineering rules: root `AGENTS.md`.

## Overview

Standalone menu-bar-only macOS app that captures ambient audio (mic + system) and screen, transcribes via Omi cloud ASR (`/v4/listen`) and on-device Parakeet (Apple Silicon only), and serves context to Claude over MCP. Two processes, one SQLite database (WAL + FTS5), no IPC — a heartbeat file carries live capture state.

- Swift 6.2 / SwiftPM, platform floor macOS 14.4, Swift language mode v5.
- Twelve MCP tools (`recall`, `recent`, `conversations`, `transcript`, `screen`, `look`, `activity`, `status`, `get_memories`, `create_memory`, `edit_memory`, `delete_memory`).
- Auto-updates via Sparkle with its own EdDSA key and bundle identity (`com.omi.context-for-claude`).

## Build & test

```bash
./scripts/build.sh --run        # build, sign, install to /Applications, launch
swift test                      # hermetic suite (no network, no live services)
python3 scripts/eval.py         # answer-quality eval over the real MCP binary (stdlib only)
```

Portable C++17 `core/` also builds standalone via CMake (see `core/README.md`).

## Layout

- `Sources/ContextCore/` — storage, queries, pure policy. No AppKit/AVFoundation (links into MCP binary).
- `Sources/ContextMCPKit/` — JSON-RPC + tool dispatch. No UI, no capture.
- `Sources/ContextMCP/` — `main.swift` only: stdin/stdout to `MCPServer`.
- `Sources/ContextApp/` — capture, transcription, menu bar, onboarding, Claude registration, auto-update.
- `core/` — portable C++17 decision rules (session boundaries, recall scoring, moment grouping) with a flat C ABI. Compiled by both SwiftPM and the Windows CMake build.
- `windows/` — Windows-only CMake proof that the portable core's C ABI links and the pinned swift-winrt generator projects Windows SDK metadata. No capture, OCR, storage, MCP, or UI on Windows.
- `scripts/` — `build.sh`, `eval.py`, `release-context.sh`, `package-dmg.sh`, `generate-appcast.py`, `uninstall.sh`, and more.
- `docs/` — `evals.md`, `releasing.md`, `analytics.md`, `design-system.md`, `first-run-experience.md`, `ocr-quality.md`.

## Release

Entry point: `scripts/release-context.sh` (delegates to `scripts/release-micro-app.sh`). Tag format: `context-for-claude-v<major>.<minor>.<patch>`. GitHub is the entire update backend — the Sparkle appcast is a mutable asset on a prerelease holder tag (`context-for-claude-appcast`). Requires `CONTEXT_SPARKLE_PUBLIC_KEY`, `CONTEXT_GITHUB_TOKEN`, `CFC_SIGN_IDENTITY`, and notarization credentials. Rehearsals: `--rehearsal` builds and signs locally without publishing. Full flow, key setup, and verification: `docs/releasing.md`.

## Relationship to other apps

Explicitly **not** part of `desktop/macos/`. Shares no code, no data, no process, no bundle identity, no Sparkle key, and no signing certificate with the Omi desktop app. Capture paths are *ported* from `desktop/macos` (CoreAudio IOProc, process-tap drift compensation, ScreenCaptureKit + Vision OCR) because they encode years of real-world corrections — but they are separate source files in this package. The portable `core/` C++17 library is the one surface compiled by both this package and the `windows/` CMake proof.

Interface contracts every file was built against: `CONTRACTS.md`. Structural decisions: `ARCHITECTURE.md`.
