# App UI verification (agent-flutter)

Reference for verifying Flutter UI changes in `app/`. Linked from `app/AGENTS.md`.

After any Flutter UI edit, verify with [agent-flutter](https://github.com/beastoin/agent-flutter) (Marionette is integrated in debug builds). Install once: `npm install -g agent-flutter-cli`.

Edit → Verify → Evidence loop:

1. Edit code, hot restart: `kill -SIGUSR2 $(pgrep -f "flutter run" | head -1)`
2. Connect: `AGENT_FLUTTER_LOG=/tmp/flutter-run.log agent-flutter connect`
3. Verify: `agent-flutter snapshot -i`
4. Interact: `agent-flutter press @e3` / `press 540 1200` / `find type button press` / `fill @e5 "text"` / `dismiss`
5. Evidence: `agent-flutter screenshot /tmp/evidence.png`

Key rules:

- Must reconnect after every hot restart (kills VM Service session).
- Refs go stale frequently — always re-snapshot before every interaction. Use `press x y` as fallback.
- `AGENT_FLUTTER_LOG` must point to flutter run stdout (not logcat).
- Prefer `find type X` / `find key "name"` over hardcoded `@ref`. Add `Key('descriptive_name')` to new interactive widgets.
- Full command reference: `agent-flutter schema`.
