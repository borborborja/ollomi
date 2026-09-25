FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
ARG VOICEPRINT_MODEL_REPOSITORY=speechbrain/spkrec-ecapa-voxceleb
# This is the full, reviewed Hugging Face revision rather than a mutable model
# branch. Update it deliberately with model/license review and a new Ollomi
# image release.
ARG VOICEPRINT_MODEL_REVISION=0f99f2d0ebe89ac095bcc5903c4dd8f72b367286
# The three checkpoint files actually loaded by SpeechBrain.  Pinning the Git
# revision makes the source reproducible; these checks make an unexpected
# changed artifact fail the image build before it can be published.
ARG VOICEPRINT_CLASSIFIER_SHA256=fd9e3634fe68bd0a427c95e354c0c677374f62b3f434e45b78599950d860d535
ARG VOICEPRINT_EMBEDDING_SHA256=0575cb64845e6b9a10db9bcb74d5ac32b326b8dc90352671d345e2ee3d0126a2
ARG VOICEPRINT_NORMALIZATION_SHA256=cd70225b05b37be64fc5a95e24395d804231d43f74b2e1e5a513db7b69b34c33
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home voiceprint
WORKDIR /srv
COPY services/voiceprint/requirements.txt /srv/requirements.txt
# PyTorch publishes its CPU wheels on this index; no CUDA runtime is installed.
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r /srv/requirements.txt \
    && mkdir /models /opt/ollomi-voiceprint-model
COPY services/voiceprint/app.py /srv/app.py
# Bake the reviewed ECAPA revision into the image. Runtime uses this local
# directory with Hugging Face offline mode, so a first boot never downloads
# model weights or needs a Hugging Face credential/network connection.
# SpeechBrain's upstream YAML names the remote repository in `paths`; the
# build rewrites that declaration to the baked directory, since merely
# supplying a local source would otherwise make its pretrainer request Hugging
# Face.
RUN python -c 'import os; from huggingface_hub import snapshot_download; snapshot_download(repo_id=os.environ["VOICEPRINT_MODEL_REPOSITORY"], revision=os.environ["VOICEPRINT_MODEL_REVISION"], local_dir="/opt/ollomi-voiceprint-model")' \
    && printf '%s  %s\n%s  %s\n%s  %s\n' \
        "$VOICEPRINT_CLASSIFIER_SHA256" /opt/ollomi-voiceprint-model/classifier.ckpt \
        "$VOICEPRINT_EMBEDDING_SHA256" /opt/ollomi-voiceprint-model/embedding_model.ckpt \
        "$VOICEPRINT_NORMALIZATION_SHA256" /opt/ollomi-voiceprint-model/mean_var_norm_emb.ckpt \
        | sha256sum --check --strict \
    && python -c 'from pathlib import Path; path = Path("/opt/ollomi-voiceprint-model/hyperparams.yaml"); path.write_text(__import__("re").sub(r"(?m)^pretrained_path: .*$", "pretrained_path: /opt/ollomi-voiceprint-model", path.read_text()))' \
    && HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -c 'from speechbrain.inference.speaker import EncoderClassifier; EncoderClassifier.from_hparams(source="/opt/ollomi-voiceprint-model", savedir="/tmp/ollomi-voiceprint-build-check", run_opts={"device": "cpu"})' \
    && rm -rf /tmp/ollomi-voiceprint-build-check
# Validate the application while the image is built. Use /tmp explicitly so
# this check also remains valid after switching to the unprivileged, read-only
# runtime filesystem below.
RUN python -c 'import py_compile; py_compile.compile("/srv/app.py", cfile="/tmp/voiceprint-app.pyc", doraise=True)' \
    && rm /tmp/voiceprint-app.pyc
# Keep Hugging Face's cache on the writable model volume when the container
# runs with a read-only root filesystem.
ENV HF_HOME=/models/huggingface XDG_CACHE_HOME=/models/cache \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    VOICEPRINT_MODEL=/opt/ollomi-voiceprint-model \
    VOICEPRINT_MODEL_DIR=/tmp/ollomi-voiceprint-runtime
USER voiceprint
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8091", "--no-access-log"]
