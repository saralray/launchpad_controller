# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Linux MIDI daemon. Bridges Novation Launchpad Mini MK3 to Home Assistant. Single-process, no build step, no tests — Python package + JSON config.

## Run / dev commands

```bash
pip install -r requirements.txt
python controller.py          # main daemon (needs Launchpad plugged in)
python -m launchpad.manage    # GUI to edit config.json macros (Tkinter; stop the daemon first so it can hold the MIDI port)
python keychecker.py          # raw note/CC printer — the manage app's Learn mode supersedes this for editing config.json
```

The manage GUI needs Tkinter (`sudo apt install python3-tk` on Ubuntu; stdlib but not always packaged). It edits `config.json` on disk only — restart the daemon to apply.

No test suite, no linter config, no package manager beyond pip. Deploy is via install script, not CI:

```bash
sudo ./install-ubuntu.sh      # or install-fedora.sh
journalctl -u launchpad_controller -f   # tail logs after install
```

Install scripts wipe and recreate `/opt/launchpad_controller`, a venv, a systemd unit, a udev rule (start-on-plug via USB vendor/product ID `1235:0113`), and a `.desktop` launcher (`/usr/share/applications/launchpad-macro-manager.desktop`, icon `assets/launchpad.svg`) that runs the manage GUI from the app menu. Re-run the installer after code changes meant for the deployed service; editing files in this repo alone has no effect on the running systemd service.

## Architecture

`controller.py` is a thin entry shim (`from launchpad.app import main`). Real logic lives in the `launchpad/` package. Kept as `controller.py` so the systemd unit / udev rule and their `WorkingDirectory` stay unchanged.

Package layout:

- **`launchpad/config.py`** — typed model (`Config` → `Room` → `Action` dataclasses) loaded from `config.json` via `load_config()`. `Action.is_preset` distinguishes preset vs entity actions. `Action.service_data` is preserved from JSON but not applied at runtime (matches historical behavior).
- **`launchpad/ha_client.py`** — `HAClient` owns the entity-state cache (`self.states`) and all Home Assistant I/O. `.passive` is set when URL/token are absent (**PASSIVE_MODE**): every network call becomes a no-op and the cache is driven only by optimistic local writes; the rest of the app treats a passive client transparently, so never assume credentials exist. Three cache writers: `refresh_states()` REST poll, a persistent `state_changed` WebSocket subscription (`start_ws`, own daemon thread), and `set_local()` optimistic writes from the controller. `call()` fires service requests in a fire-and-forget daemon thread so LEDs update instantly rather than waiting on HA.
- **`launchpad/settings.py`** — `get_credentials()` resolves the HA URL/token from `settings.json` (next to `config.json`), falling back to `.env`/environment. `settings.json` is written by the manage GUI's Connection dialog (`save_settings`, chmod 600, git-ignored) — `.env` is optional, not required. Both `app.main()` and the manage GUI read through `get_credentials`. The daemon reads credentials only at startup, so restart it after changing the connection.
- **`launchpad/midi.py`** — `MidiSurface`: port discovery, hot-plug detection, LED output. `open()` blocks/retries until both Launchpad in/out ports appear; never lets exceptions escape. Port selection goes through `device.pick_launchpad_port`, which returns the **first** Launchpad port the OS exposes (same port keychecker and the manage GUI use, for in and out alike). **No layout is forced** anywhere — the app works off the device's *real* emitted note/CC numbers in whatever layout it's in; config.json and the calibration wizard must match those actual numbers. `device.layout_sysex` / `midi.set_programmer_mode` remain available but are no longer called on connect.
- **`launchpad/presets_api.py`** — `PresetHA`, the façade handed to preset `run(ha)`. Exposes exactly `all_lights` / `is_on` / `turn_on` / `turn_off`; presets talk only to this, never to `HAClient` or the cache directly.
- **`launchpad/app.py`** — `Controller` owns runtime state and the event loop, plus `main()` (env load, wiring, signal handlers).
- **`launchpad/config.py` serialization** — `Action.to_dict` / `Room.to_dict` / `Config.to_dict` + `save_config()` write the model back to `config.json`. Used by the manage GUI; round-trip preserves `service_data`, colors, and `room_key_color_on`.
- **`launchpad/manage.py`** — Tkinter macro editor (`python -m launchpad.manage`). Left: rooms list; middle: 9x9 grid preview + Unplaced-actions list; right: macro editor (pad number, entity/preset type, entity picker, on/off colors). `MidiBridge` opens the Launchpad input in a thread for **Learn mode** (press a physical pad → its note/CC fills the focused field) and the output for live color preview — so the daemon must be stopped first (one process per port). The **Map layout** button runs `LayoutWizard`, a full-surface calibration: it steps through every grid position, records the button pressed there, and saves `layout.json` (MIDI events route to the wizard via `map_capture`, taking priority over `learn_target`). Entities are fetched via `HAClient` using credentials from `get_credentials()` (settings.json / .env), configured in-app via the **Connection** dialog (`_open_connection`); falls back to free-text in passive mode. Edits touch `config.json` on disk only; the running daemon must be restarted to pick them up.
- **`launchpad/palette.py`** — coarse velocity→RGB approximation for GUI swatches only; exact color is previewed on the device.
- **`launchpad/layout.py`** — `Layout`: bidirectional position↔event map used by the manage GUI to place macros on the grid. Keyed on `(is_cc, number)`, not number alone — the scene column and a main pad can emit the same numeric value differing only in message type (note_on vs control_change), and a CC room-selector can share a numeric value with a note action. Learned cells override the documented Mini MK3 formula (`default_key_for_cell`); cells left uncalibrated fall back to it, so a partial map still places everything. The "Map layout" wizard persists learned cells to `layout.json` (git-ignored, per-device).
- **Grid geometry** (`layout.default_key_for_cell`): the pre-calibration guess — top CC row 91-99, right scene column 19-89, main 8x8 notes 11-88 (tens=row-from-bottom, ones=column). Injective across the 81 cells. Numbers off this grid (e.g. the shipped config's note 60/90) can't be placed and appear in the Unplaced list, still fully editable. The **Map layout** wizard (`manage.LayoutWizard`) overrides this: it steps through the 72 calibratable cells (the 8x8 grid + right scene column — the top-bar CC row and the top-right logo are excluded), records the physical button pressed at each, and writes `layout.json` — so a unit in a nonstandard layout mode still maps correctly. Unmapped cells (the top bar) stay on the formula. Purely a GUI-authoring aid; the daemon acts on raw config numbers and never reads `layout.json`.

Behavior notes:

- **Room model** (`config.json`): a list of `rooms`, each with a `room_key` (`control_change` number — top-row buttons select the active room) and `actions` (`note_on` numbers — grid buttons). Only one room is active at a time (`Controller.active_room`); grid presses act on `active_room.actions` only.
- **Action shape**: each action is either `entity_ids` (toggle one or more HA entities together, tracked via `on_color`/`off_color`) or `preset` (dispatches to `presets/<name>.py`).
- **Presets** (`presets/*.py`): each module exposes `run(ha)` and is loaded via `importlib.import_module(f"presets.{name}")` in `Controller.run_preset`. `ha` is `PresetHA`. Long-running presets (`wave`, `chaos`) use module-level `_running` flags and background threads and expose `stop()`/`stop(ha)`. When adding a preset, register it in `config.json` under the `Presets` room's `actions` with `"preset": "<module_name>"`. `presets/` stays a top-level package (not under `launchpad/`) so the `presets.<name>` import path keeps working.
- **Main loop** (`Controller.run`): polls `midi.iter_pending()` at ~100Hz. `control_change` switches `active_room`; `note_on` with velocity > 0 triggers the matching action. Every state change calls `update_pads()`, rate-limited to ~12.5Hz (`PAD_REFRESH_INTERVAL = 0.08`), repainting room-select LEDs (any-entity-on) plus the active room's grid LEDs. An entity counts as "lit" when its state is in `ON_STATES = ("on", "cool")`; note `PresetHA.is_on` deliberately checks `== "on"` only, matching the original preset semantics.
- **USB resilience**: `MidiSurface.open()` blocks until both ports are found; the loop calls `still_present()` each iteration and silently reconnects on unplug/replug without crashing or restarting the process. Preserving this (no exceptions escaping the loop, no `BindsTo=` in the systemd unit) is a core design goal.

## Editing config.json

- `room_key` values come from `control_change` messages (top row); `key` values inside `actions` come from `note_on` messages (grid). Use `keychecker.py` against the physical device to get real numbers — don't guess them.
- Color values are Launchpad Mini MK3 palette indices (velocity values sent via `note_on`/`control_change`), not RGB.
