# Ollomi fork publishing (autonomous)

Reference for the root `AGENTS.md` "Safety Rules" publishing exception in the `borborborja/ollomi` fork.

- A request to publish Docker images, an APK, or a release **is** the authorization. The agent may then:
  - create and push a feature branch, open its PR, and regularly merge it (regular merge, never squash);
  - create the next patch release;
  - wait for the `Publish Ollomi` workflow (`.github/workflows/ollomi-release.yml`), repair failures, and re-run it;
  - verify the public GHCR images (`ollomi-api`, `ollomi-stt`, `ollomi-voiceprint`) and the release assets (`ollomi.apk`, `ollomi-backend.tar.gz`, `SHA256SUMS`) without asking again.
- This exception **never** authorizes a direct push to `main`, and never authorizes an upstream `BasedHardware/omi` release.
- A prior approval never carries over to later changes.
