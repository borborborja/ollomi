# Ollomi Voiceprint service

This is the optional CPU-only companion that lets Ollomi identify the account
owner's voice across recordings. It uses SpeechBrain ECAPA to turn the short
enrollment recording and diarized clip excerpts into embeddings. When the STT
does not return speaker turns (for example, a standard OpenAI/Whisper endpoint),
it also provides a CPU-only, energy-gated ECAPA speaker-turn fallback. Native
STT diarization from Gemini, Deepgram or AssemblyAI always takes precedence.
The main Ollomi database stores only the encrypted enrollment embedding, never
the raw enrollment audio.

Deploy it on the separate x86-64 server chosen for models. From a source
checkout, use the build Compose file:

```sh
cp env.example .env
# set a long random VOICEPRINT_API_KEY
docker compose up -d --build
```

After the same Ollomi fork has published a reviewed release, the server needs
only the published Compose file and `.env`; it does not need a checkout:

```sh
mkdir ollomi-voiceprint && cd ollomi-voiceprint
curl -LO https://raw.githubusercontent.com/YOUR_GITHUB_OWNER/ollomi/main/deploy/examples/voiceprint/compose.ghcr.yaml
curl -Lo .env https://raw.githubusercontent.com/YOUR_GITHUB_OWNER/ollomi/main/deploy/examples/voiceprint/env.example
# Set VOICEPRINT_API_KEY, OLLOMI_IMAGE_OWNER and OLLOMI_IMAGE_TAG in .env.
chmod 600 .env
docker compose -f compose.ghcr.yaml config --quiet
docker compose -f compose.ghcr.yaml pull
docker compose -f compose.ghcr.yaml up -d
```

Expose port 8091 only to the Ollomi backend (a VPN/private network or an HTTPS
reverse proxy). On the main stack set:

```dotenv
OLLOMI_VOICEPRINT_URL=https://voiceprint.example.internal
OLLOMI_VOICEPRINT_API_KEY=the_same_value_as_VOICEPRINT_API_KEY
OLLOMI_VOICEPRINT_THRESHOLD=0.72
```

The reviewed ECAPA model is downloaded, pinned and checksum-verified while the
image is built or published, not at first boot. The running container has
Hugging Face offline mode enabled; it needs neither a Hugging Face credential
nor Internet access. `VOICEPRINT_MODEL_REPOSITORY` and
`VOICEPRINT_MODEL_REVISION` affect only the source-build image, and changing
them requires model/license and checksum review, a rebuilt image and
re-enrolment. The service is CPU-only and has no access to the Ollomi database,
audio volume, or account credentials.

The local fallback is intended to distinguish short turns in ordinary
conversations, not as forensic speaker attribution. Validate its threshold on
representative recordings before enabling it for consequential workflows; the
service is optional and a temporary failure never blocks transcription.
