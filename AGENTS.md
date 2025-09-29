# Repository Guidelines

## Project Structure & Modules
- Core: `engine.py`, `engine_factory.py`, `synth.py`, `controls.py` — engine logic, synthesis, and control mapping.
- I/O: `audio_device.py`, `audio_tools.py` — PyAudio device selection and streaming helpers.
- Apps: `main.py` (simulator entry), `mainspectrometer.py` (visualization), `spectrometer.py`.
- Config: `cfg.py` for tunables (channels, blending, engine presets).
- Utilities: `engine_single_buffer.py`, `test.py` (manual/demo test).
- Assets: none committed; audio is generated at runtime.

## Build, Run, and Dev Commands
- Create venv (recommended): `python -m venv .venv && source .venv/bin/activate` (Windows: `.venv\\Scripts\\activate`).
- Install deps: `pip install -r requirements.txt` (Windows helper: `Install Requirements.bat`).
- Run simulator: `python main.py`.
- Run spectrometer demo: `python mainspectrometer.py`.
- Manual test/smoke: `python test.py`.

## Coding Style & Naming
- Python 3.9+, 4-space indents, PEP 8 naming (`snake_case` for functions/vars, `PascalCase` for classes, `UPPER_SNAKE` for constants).
- Prefer small, pure functions in `engine_*` modules; keep device-specific code in `audio_*`.
- Type hints where practical; docstrings for public functions/classes. Keep modules under ~500 lines; split if needed.

## Testing Guidelines
- No formal framework yet. Use `test.py` and targeted scripts for repros.
- Add minimal, headless checks (e.g., buffer length, RMS range) so tests don’t require an audio device.
- Place ad-hoc tests beside modules as `module_name_demo.py` or `module_name_test.py` and document usage at the top.

## Commit & Pull Requests
- Commits: imperative, concise subject (≤72 chars), body explains why and any audio/perf impact.
  - Example: `engine: reduce buffer underruns by doubling chunk size`.
- PRs: include purpose, key changes, manual run steps, and environment (OS, Python, device/driver). Screenshots/plots from `mainspectrometer.py` are helpful.
- Link related issues and note any config changes in `cfg.py` defaults.

## Platform & Audio Notes
- PyAudio/portaudio backends vary by OS. On Linux ensure ALSA permissions; on Windows, select the correct WASAPI device in `audio_device.py` if needed.
- Avoid blocking calls in audio callbacks; keep them allocation-free.

## Chat Languages
- The agent should always speak in Chinese.
