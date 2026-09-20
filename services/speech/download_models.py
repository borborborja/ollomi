#!/usr/bin/env python3
"""Download approved faster-whisper models into the self-hosted model directory."""

import argparse
from pathlib import Path

WHISPER_MODELS = {
    name: f"Systran/faster-whisper-{name}" for name in ("tiny", "base", "small", "medium", "large-v2", "large-v3")
}


def destination(models_dir: Path, model: str) -> Path:
    if model not in WHISPER_MODELS:
        raise ValueError(f"Unsupported Whisper model: {model}")
    return models_dir / model


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ollomi-download-models")
    parser.add_argument("--stt", choices=sorted(WHISPER_MODELS), default="small")
    parser.add_argument("--models-dir", type=Path, default=Path("/models"))
    args = parser.parse_args(argv)

    from huggingface_hub import snapshot_download

    target = destination(args.models_dir, args.stt)
    target.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {WHISPER_MODELS[args.stt]} to {target}")
    snapshot_download(WHISPER_MODELS[args.stt], local_dir=target)
    print(f"Whisper model {args.stt} is ready")


if __name__ == "__main__":
    main()
