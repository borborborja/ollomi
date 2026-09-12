# Speech components and model licenses

The original Omi MIT license is preserved. This separate Docker service installs third-party components; their licenses are not replaced by the repository's MIT license.

- faster-whisper: MIT, https://github.com/SYSTRAN/faster-whisper
- Piper (`piper-tts`, OHF-Voice/piper1-gpl): GPL-3.0, https://github.com/OHF-Voice/piper1-gpl. Preserve the license and satisfy source-distribution requirements when distributing an image containing it. Corresponding upstream source for the pinned version is available from that project.
- pyannote.audio: MIT software; Community-1 weights have their own model card, conditions and download gate: https://huggingface.co/pyannote/speaker-diarization-community-1
- Piper voices have individual model cards. Download the `.onnx`, `.onnx.json` and model card together; retain the model's own license and attribution.
- Whisper/Ollama model weights are provisioned separately. Consult each model's card and retain its license/revision. No model weights are committed to this repository.

The optional diarization build and CUDA image have additional third-party dependencies. This file identifies the key choices; it is not a substitute for the licenses bundled with each package/image.
