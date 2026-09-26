# Deploy surfaces & break-glass hatches (upstream reference)

This fork ships through `.github/workflows/ollomi-release.yml` (`Publish Ollomi`). The surfaces below belong to upstream `BasedHardware/omi` and are **not present in this fork**; they are kept as reference.

- Desktop (hourly candidate → signed-smoke Beta → manual Stable): `desktop/macos/AGENTS.md` → Release Pipeline.
- Backend: `gcp_backend.yml` is the main stack (`environment`, `release_sha`, `release_version`, `mode`, `deploy_targets`; no `branch`). Prod `release_sha` needs a first-attempt Release Eligibility proof. desktop-backend: `desktop_backend_prod.yml` (`release_sha`, confirm `deploy-desktop-backend-prod`, reason).
- Firmware (Omi CV1): `omi/firmware/AGENTS.md`.

**Every gated surface has a break-glass hatch. A broken gate is never a reason to be stuck.** Each records a tracking issue; repeated use means the gate is the defect.

| Blocked on | Hatch |
|---|---|
| Desktop candidate won't cut (`Desktop Swift Build & Tests` red/flaky) | `desktop_auto_release.yml` with `release_mode=break_glass` |
| Backend deploy has no Release Eligibility proof | `gcp_backend.yml` with `skip_eligibility_proof=true`, `break_glass_confirm=deploy-without-proof`, `break_glass_reason` |

Hatches relax *evidence* requirements only. They never relax that code is merged to `main` first, and never reach stable/prod pointers without their own explicit confirm.
