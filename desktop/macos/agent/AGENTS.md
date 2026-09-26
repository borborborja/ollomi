# desktop/macos/agent — Agent Guide

Component guide for `desktop/macos/agent/`. General engineering rules: root `AGENTS.md`; the macOS app itself is covered by `desktop/macos/AGENTS.md`.

## Overview

Node/TypeScript agent runtime harness used by the macOS app. Owns durable agent identity, execution profiles, routing, context admission, run/attempt state, physical-tool authorization, and the cross-surface conversation journal. Swift is a transport and presentation client; adapters execute model work but do not own policy. Full architecture: `src/ARCHITECTURE.md`.

## Layout

- `src/protocol.ts` — versioned JSONL transport boundary (every message crossing Swift/Node)
- `src/index.ts` — transport envelope validation, physical I/O to kernel operations
- `src/runtime/kernel.ts` — public kernel facade; split `kernel-{core,sessions,runs,coordinator,artifacts}.ts`
- `src/runtime/` — kernel internals: `desktop-intent-router.ts`, `external-surface-tool-policy.ts`, `context-snapshot.ts`, `conversation-journal.ts`, `sqlite-store.ts`, etc.
- `src/adapters/` — model-provider execution: `acp.ts`, `hermes.ts`, `openclaw.ts`, `pi-mono.ts`, `interface.ts`
- `tests/` — 74 Vitest test files (~33k lines), hermetic behavioral coverage
- `contracts/v1/`, `evals/`, `fixtures/`, `scripts/` — contract schema + fixtures, realtime routing eval cases, spawn-receipt fixtures, eval runners/generators

## Build & test

```bash
npm run build        # tsc && cp src/patched-acp-entry.mjs dist/patched-acp-entry.mjs
npm test             # vitest run (15s test timeout, 20s hook timeout)
npm run eval:realtime-routing  # build + node scripts/eval-realtime-routing.mjs
```

TypeScript: ES2022, NodeNext modules, strict, `outDir: dist`, `rootDir: src`.

## Contracts/evals

- `contracts/v1/agent-runtime-contract.schema.json` — authoritative schema; `*.fixture.json` are valid/malformed test inputs
- `evals/realtime-routing-cases.json` — prompt/expected-tool/kind cases
- Contract tests: `tests/agent-runtime-contract-fixtures.test.ts`, `tests/runtime-adapter-contract-conformance.test.ts`

## Gotchas

- Vitest timeouts bounded (15s test, 20s hook) to contain hangs on shared CI runners
- `protocol.ts` is the authority boundary — new authority-bearing operations must be typed there
- `index.ts` must not reimplement routing, profile, journal, or capability policy
- `desktop-intent-router.ts` is the sole semantic route decision owner; adapters execute model work only
- macOS `AGENTS.md` "Agent Logic Harness" covers the focused harness; this guide covers internals