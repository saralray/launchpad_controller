#!/usr/bin/env python3
# launchpad_controller.py

import mido
import requests
import json
import time
import threading
import websocket
import urllib3
import os
import signal
import sys
import importlib
from dotenv import load_dotenv

# ============================================================
# ENV
# ============================================================

load_dotenv()

HASS_URL = os.getenv("HASS_URL")
HASS_TOKEN = os.getenv("HASS_TOKEN")
PASSIVE_MODE = not (HASS_URL and HASS_TOKEN)

HEADERS = {
    "Authorization": f"Bearer {HASS_TOKEN}",
    "Content-Type": "application/json",
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# GLOBAL STATE CACHE (🔥 FAST)
# ============================================================

HA_STATES = {}
HA_STATES_TS = 0

inport = None
outport = None
current_in_name = None
current_out_name = None
_last_update = 0

# ============================================================
# SHUTDOWN
# ============================================================

def shutdown(sig, frame):
    print("🛑 Shutting down...")
    try:
        if inport:
            inport.close()
        if outport:
            outport.close()
    except Exception:
        pass
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

# ============================================================
# MIDI
# ============================================================

def open_ports():
    global inport, outport, current_in_name, current_out_name
    while True:
        ins = mido.get_input_names()
        outs = mido.get_output_names()

        in_name = next((p for p in ins if "launchpad" in p.lower() and "da" in p.lower()), None)
        out_name = next((p for p in outs if "launchpad" in p.lower()), None)

        if in_name and out_name:
            inport = mido.open_input(in_name)
            outport = mido.open_output(out_name)
            current_in_name = in_name
            current_out_name = out_name
            print(f"✅ Connected: {in_name}")
            return

        time.sleep(1)

def ports_still_present():
    try:
        return (
            current_in_name in mido.get_input_names()
            and current_out_name in mido.get_output_names()
        )
    except Exception:
        return False

# ============================================================
# HOME ASSISTANT (NON-BLOCKING)
# ============================================================

def call_ha(domain, svc, data):
    if PASSIVE_MODE:
        return
    threading.Thread(
        target=requests.post,
        kwargs=dict(
            url=f"{HASS_URL}/api/services/{domain}/{svc}",
            headers=HEADERS,
            json=data,
            timeout=3,
            verify=False,
        ),
        daemon=True,
    ).start()

def get_states(force=False):
    global HA_STATES, HA_STATES_TS

    if PASSIVE_MODE:
        return HA_STATES

    if not force and time.time() - HA_STATES_TS < 0.5:
        return HA_STATES

    try:
        r = requests.get(
            f"{HASS_URL}/api/states",
            headers=HEADERS,
            timeout=3,
            verify=False,
        )
        r.raise_for_status()
        HA_STATES = {s["entity_id"]: s for s in r.json()}
        HA_STATES_TS = time.time()
    except Exception:
        pass

    return HA_STATES

# ============================================================
# PRESET HA INTERFACE (ONLY API PRESETS USE)
# ============================================================

class HA:
    def all_lights(self):
        return [e for e in HA_STATES if e.startswith("light.")]

    def is_on(self, entity_id):
        return HA_STATES.get(entity_id, {}).get("state") == "on"

    def turn_on(self, entity_id, **data):
        HA_STATES[entity_id] = {"state": "on"}
        call_ha("light", "turn_on", {"entity_id": entity_id, **data})

    def turn_off(self, entity_id):
        HA_STATES[entity_id] = {"state": "off"}
        call_ha("light", "turn_off", {"entity_id": entity_id})

ha = HA()

def run_preset(name):
    try:
        importlib.import_module(f"presets.{name}").run(ha)
    except Exception as e:
        print(f"❌ Preset error [{name}]: {e}")

# ============================================================
# LED OUTPUT
# ============================================================

def set_pad(key, val, is_cc):
    if not outport:
        return
    outport.send(
        mido.Message("control_change", control=key, value=val)
        if is_cc
        else mido.Message("note_on", note=key, velocity=val)
    )

def update_pads():
    global _last_update
    if time.time() - _last_update < 0.08:
        return
    _last_update = time.time()

    for room in rooms:
        any_on = any(
            "entity_ids" in a
            and any(HA_STATES.get(e, {}).get("state") in ("on", "cool") for e in a["entity_ids"])
            for a in room["actions"]
        )
        set_pad(
            room["room_key"],
            room.get("room_key_color_any_on", 9)
            if any_on
            else room.get("room_key_color_off", 5),
            True,
        )

    for act in active_room["actions"]:
        if "entity_ids" not in act:
            set_pad(act["key"], act["on_color"], False)
        else:
            on = any(
                HA_STATES.get(e, {}).get("state") in ("on", "cool")
                for e in act["entity_ids"]
            )
            set_pad(act["key"], act["on_color"] if on else act["off_color"], False)

# ============================================================
# WEBSOCKET (STATE SOURCE OF TRUTH)
# ============================================================

def _on_ws_message(ws, msg):
    global HA_STATES, HA_STATES_TS
    try:
        d = json.loads(msg)
        e = d.get("event", {}).get("data", {})
        if "entity_id" in e and "new_state" in e:
            HA_STATES[e["entity_id"]] = e["new_state"]
            HA_STATES_TS = time.time()
            update_pads()
    except Exception:
        pass

def _on_ws_open(ws):
    ws.send(json.dumps({"type": "auth", "access_token": HASS_TOKEN}))
    ws.send(
        json.dumps(
            {
                "id": 1,
                "type": "subscribe_events",
                "event_type": "state_changed",
            }
        )
    )

def _start_ws():
    if PASSIVE_MODE:
        return
    ws_url = HASS_URL.replace("http", "ws") + "/api/websocket"
    while True:
        try:
            websocket.WebSocketApp(
                ws_url, on_open=_on_ws_open, on_message=_on_ws_message
            ).run_forever()
        except Exception:
            time.sleep(3)

# ============================================================
# MAIN
# ============================================================

open_ports()

with open("config.json") as f:
    rooms = json.load(f)["rooms"]

active_room = rooms[0]

get_states(force=True)
threading.Thread(target=_start_ws, daemon=True).start()

print("🚀 FAST Controller Started")
update_pads()

while True:
    if not ports_still_present():
        open_ports()
        update_pads()

    for msg in inport.iter_pending():
        if msg.type == "control_change":
            for r in rooms:
                if r["room_key"] == msg.control:
                    active_room = r
                    update_pads()

        elif msg.type == "note_on" and msg.velocity > 0:
            for act in active_room["actions"]:
                if msg.note != act["key"]:
                    continue

                if "preset" in act:
                    run_preset(act["preset"])
                    update_pads()
                    break

                ids = act["entity_ids"]
                turning_on = not any(
                    HA_STATES.get(e, {}).get("state") in ("on", "cool")
                    for e in ids
                )

                for e in ids:
                    HA_STATES[e] = {"state": "on" if turning_on else "off"}
                    call_ha(
                        e.split(".")[0],
                        "turn_on" if turning_on else "turn_off",
                        {"entity_id": e},
                    )

                update_pads()
                break

    time.sleep(0.01)
