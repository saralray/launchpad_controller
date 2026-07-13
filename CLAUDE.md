# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Linux MIDI daemon. Bridges Novation Launchpad Mini MK3 to Home Assistant. Single-process, no build step, no tests — Python package + JSON config.

## Run / dev commands

```bash
pip install -r requirements.txt
python controller.py          # main daemon (needs Launchpad plugged in)
python keychecker.py          # discover note/CC numbers for a physical button — run this first when editing config.json
```

No test suite, no linter config, no package manager beyond pip. Deploy is via install script, not CI:

```bash
sudo ./install-ubuntu.sh      # or install-fedora.sh
journalctl -u launchpad_controller -f   # tail logs after install
```

Install scripts wipe and recreate `/opt/launchpad_controller`, a venv, a systemd unit, and a udev rule (start-on-plug via USB vendor/product ID `1235:0113`). Re-run the installer after code changes meant for the deployed service; editing files in this repo alone has no effect on the running systemd service.

## Architecture

`controller.py` is a thin entry shim (`from launchpad.app import main`). Real logic lives in the `launchpad/` package. Kept as `controller.py` so the systemd unit / udev rule and their `WorkingDirectory` stay unchanged.

Package layout:

- **`launchpad/config.py`** — typed model (`Config` → `Room` → `Action` dataclasses) loaded from `config.json` via `load_config()`. `Action.is_preset` distinguishes preset vs entity actions. `Action.service_data` is preserved from JSON but not applied at runtime (matches historical behavior).
- **`launchpad/ha_client.py`** — `HAClient` owns the entity-state cache (`self.states`) and all Home Assistant I/O. `.passive` is set when URL/token are absent (**PASSIVE_MODE**): every network call becomes a no-op and the cache is driven only by optimistic local writes; the rest of the app treats a passive client transparently, so never assume `.env` exists. Three cache writers: `refresh_states()` REST poll, a persistent `state_changed` WebSocket subscription (`start_ws`, own daemon thread), and `set_local()` optimistic writes from the controller. `call()` fires service requests in a fire-and-forget daemon thread so LEDs update instantly rather than waiting on HA.
- **`launchpad/midi.py`** — `MidiSurface`: port discovery, hot-plug detection, LED output. `open()` blocks/retries until both Launchpad in/out ports appear; never lets exceptions escape.
- **`launchpad/presets_api.py`** — `PresetHA`, the façade handed to preset `run(ha)`. Exposes exactly `all_lights` / `is_on` / `turn_on` / `turn_off`; presets talk only to this, never to `HAClient` or the cache directly.
- **`launchpad/app.py`** — `Controller` owns runtime state and the event loop, plus `main()` (env load, wiring, signal handlers).

Behavior notes:

- **Room model** (`config.json`): a list of `rooms`, each with a `room_key` (`control_change` number — top-row buttons select the active room) and `actions` (`note_on` numbers — grid buttons). Only one room is active at a time (`Controller.active_room`); grid presses act on `active_room.actions` only.
- **Action shape**: each action is either `entity_ids` (toggle one or more HA entities together, tracked via `on_color`/`off_color`) or `preset` (dispatches to `presets/<name>.py`).
- **Presets** (`presets/*.py`): each module exposes `run(ha)` and is loaded via `importlib.import_module(f"presets.{name}")` in `Controller.run_preset`. `ha` is `PresetHA`. Long-running presets (`wave`, `chaos`) use module-level `_running` flags and background threads and expose `stop()`/`stop(ha)`. When adding a preset, register it in `config.json` under the `Presets` room's `actions` with `"preset": "<module_name>"`. `presets/` stays a top-level package (not under `launchpad/`) so the `presets.<name>` import path keeps working.
- **Main loop** (`Controller.run`): polls `midi.iter_pending()` at ~100Hz. `control_change` switches `active_room`; `note_on` with velocity > 0 triggers the matching action. Every state change calls `update_pads()`, rate-limited to ~12.5Hz (`PAD_REFRESH_INTERVAL = 0.08`), repainting room-select LEDs (any-entity-on) plus the active room's grid LEDs. An entity counts as "lit" when its state is in `ON_STATES = ("on", "cool")`; note `PresetHA.is_on` deliberately checks `== "on"` only, matching the original preset semantics.
- **USB resilience**: `MidiSurface.open()` blocks until both ports are found; the loop calls `still_present()` each iteration and silently reconnects on unplug/replug without crashing or restarting the process. Preserving this (no exceptions escaping the loop, no `BindsTo=` in the systemd unit) is a core design goal.

## Editing config.json

- `room_key` values come from `control_change` messages (top row); `key` values inside `actions` come from `note_on` messages (grid). Use `keychecker.py` against the physical device to get real numbers — don't guess them.
- Color values are Launchpad Mini MK3 palette indices (velocity values sent via `note_on`/`control_change`), not RGB.
