"""App-managed settings (Home Assistant credentials).

Credentials live in settings.json next to config.json, written by the manage
GUI's Connection dialog — no .env required. Resolution order:

    settings.json  ->  environment / .env  (back-compat fallback)

The file holds a long-lived token, so it is written 0600 and should never be
committed (see .gitignore).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = PROJECT_ROOT / "settings.json"


def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(data: dict) -> None:
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    try:
        os.chmod(SETTINGS_PATH, 0o600)  # contains a token
    except OSError:
        pass


def programmer_mode() -> bool:
    """Whether to put the Launchpad in Programmer layout on connect.

    Defaults to True: config.json is authored for the Programmer ('User')
    layout — that's the layout whose numbering is main grid 11-88 (note_on),
    top row 91-99 and right scene column 89..19 (control_change), which is
    exactly what config.json uses (grid notes, room keys CC 89/79/69/29). In
    Live layout those LED/note numbers don't address the pads, so the surface
    stays dark. Set "launchpad_programmer_mode": false in settings.json only
    for a config authored against the Live layout.
    """
    return bool(load_settings().get("launchpad_programmer_mode", True))


def get_credentials() -> tuple[str | None, str | None]:
    """Return (url, token), preferring settings.json, then .env/environment."""
    s = load_settings()
    url = s.get("hass_url") or None
    token = s.get("hass_token") or None
    if url and token:
        return url, token
    load_dotenv()
    return url or os.getenv("HASS_URL"), token or os.getenv("HASS_TOKEN")
