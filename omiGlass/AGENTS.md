# omiGlass — Agent Guide

Component guide for `omiGlass/`. General engineering rules: root `AGENTS.md`.

## Overview

omiGlass (OpenGlass) is a separate wearable product: open-source smart glasses with AI capabilities. Stack: ESP32-S3 XIAO firmware (Arduino/PlatformIO) + React Native/Expo companion app. Distinct from `omi/` (Zephyr RTOS firmware + Flutter app).

## Layout

- `firmware/` — PlatformIO/Arduino firmware for Seeed XIAO ESP32S3. Entry: `firmware/firmware.ino`, config: `firmware/platformio.ini`, scripts: `firmware/scripts/` (build_uf2.sh, flash_esp32.sh).
- `sources/` — React Native/Expo companion app. Entry: `App.tsx`, config: `app.json`, `package.json`. Subdirs: `sources/app/` (DeviceView, Main, components), `sources/agent/` (Agent, imageDescription), `sources/modules/` (ollama, groq-llama3, openai, imaging, useDevice), `sources/utils/`.
- `hardware/` — STL files for 3D-printed frames and covers.
- `prompts/` — Prompt generation scripts (`prompts/generate.ts`, `prompts/series_1/`).
- `assets/`, `patches/`, `public/` — App resources, patch-package overrides, web assets.

## Build/test

Companion app: `npm install` then `npm start` (Expo). Web: `npm run web`. Firmware (PlatformIO): `platformio run -e seeed_xiao_esp32s3` from `firmware/`, or `firmware/scripts/build_uf2.sh` for UF2. Firmware (Arduino-CLI): see `firmware/readme.md`. No automated test suite in this component.

## Relationship to `omi/`

omiGlass is a standalone product with its own firmware (Arduino framework, not Zephyr) and companion app (React Native/Expo, not Flutter). No shared code with `omi/firmware/` or `app/`. Backend integration: omiGlass app talks to Ollama/Groq/OpenAI directly; it does not use `backend/` APIs.
