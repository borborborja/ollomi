#!/usr/bin/env python3
"""Explicit installation step; may use the Internet. The inference service cannot."""
import argparse
from pathlib import Path

from huggingface_hub import snapshot_download

parser = argparse.ArgumentParser()
parser.add_argument('model', nargs='?', default='small')
parser.add_argument('--revision', default='main')
args = parser.parse_args()
if args.model not in {'tiny', 'base', 'small', 'medium', 'large-v3', 'large-v3-turbo'}:
    parser.error('Use a known Whisper model name; mount custom CTranslate2 models manually.')
destination = Path(__file__).resolve().parents[1] / 'selfhost-data/models' / args.model
snapshot_download('Systran/faster-whisper-' + args.model, revision=args.revision, local_dir=destination)
print(destination)
