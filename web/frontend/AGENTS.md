# web/frontend — Agent Guide

Component guide for `web/frontend/`. General engineering rules: root `AGENTS.md`.

## Overview

Public website — Next.js App Router, TypeScript, Tailwind CSS, Radix UI / shadcn.
Shared-conversation pages, apps marketplace (`/apps`), `/create-app`, `/wrapped`,
`/unlimited`. Cloud Run at `https://h.omi.me`. Not the signed-in client (`web/app`).
Firebase (auth/Firestore), Algolia (search), Redis (caching). Env: `.env.template`.

## Setup & Commands

```bash
cd web/frontend
npm ci && cp .env.template .env.local && npm run dev   # localhost:3000
```

Package manager: **npm** (`web/frontend/package-lock.json`). Never bun or pnpm.

| Task | Command |
|---|---|
| Dev / Build | `npm run dev` / `npm run build` |
| Lint / Format | `npm run lint` / `npm run lint:format` |
| Test | `npm test` (`node --test src/__tests__/*.test.mjs`) |

## Quality Gates

- **Lint:** ESLint (`web/frontend/.eslintrc.cjs`) — `@typescript-eslint`, `react`,
  `jsx-a11y`, `prettier` plugin.
- **Format:** Prettier (`web/frontend/.prettierrc.js`) — single quotes, 90-col.
- **Tests:** `scripts/run-web-frontend-tests.sh` (manifest: `web-frontend-tests`).
- **Deploy:** `.github/actions/deploy-public-build/action.yml` — build contract
  `config/public-build-contract.json`.

## Sibling Apps

Four independent Next.js projects under `web/` (no npm workspaces):

| Project | Manager | Guide |
|---|---|---|
| `web/app` | Bun | `web/app/AGENTS.md` |
| `web/admin` | npm | `web/admin/AGENTS.md` |
| `web/frontend` | npm | this file |
| `web/personas-open-source` | npm | — |
