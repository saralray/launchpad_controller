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
from dotenv import load_dotenv

# ============================================================
# ENV / CONFIG
# ============================================================

load_dotenv()

HASS_URL   = os.getenv("HASS_URL")
HASS_TOKEN = os.getenv("HASS_TOKEN")

PASSIVE_MODE = not (HASS_URL and HASS_TOKEN)

HEADERS = {
    "Authorization": f"Bearer {HASS_TOKEN}",
    "Content-Type": "application/json"
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# GLOBALS
# ============================================================

inport = None
outport = None
current_in_name = None
current_out_name = None
_last_update = 0

# ============================================================
# SHUTDOWN (systemd-safe)
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
# MIDI SETUP (PASSIVE – NO MODE SWITCH)
# ============================================================

def open_ports():
    """Wait for Launchpad, open DA input + MI output."""
    global inport, outport, current_in_name, current_out_name

    while True:
        try:
            ins  = mido.get_input_names()
            outs = mido.get_output_names()
        except Exception:
            time.sleep(2)
            continue

        in_name = next(
            (p for p in ins if "launchpad" in p.lower() and "da" in p.lower()),
            None
        )

        out_name = next(
            (p for p in outs if "launchpad" in p.lower()),
            None
        )

        if in_name and out_name:
            try:
                inport  = mido.open_input(in_name)
                outport = mido.open_output(out_name)
                current_in_name = in_name
                current_out_name = out_name
                print(f"✅ Connected: {in_name} / {out_name}")
                return
            except Exception as e:
                print("❌ MIDI open error:", e)

        print("🔄 Waiting for Launchpad...")
        time.sleep(2)

def ports_still_present():
    """Check if the previously opened MIDI ports still exist."""
    if not current_in_name or not current_out_name:
        return False
    try:
        ins  = mido.get_input_names()
        outs = mido.get_output_names()
        return current_in_name in ins and current_out_name in outs
    except Exception:
        return False

# ============================================================
# HOME ASSISTANT
# ============================================================

def call_ha(domain, svc, data):
    if PASSIVE_MODE:
        return
    try:
        requests.post(
            f"{HASS_URL}/api/services/{domain}/{svc}",
            headers=HEADERS,
            json=data,
            timeout=3,
            verify=False
        )
    except Exception as e:
        print("❌ HA error:", e)

def get_states():
    if PASSIVE_MODE:
        return {}
    try:
        r = requests.get(
            f"{HASS_URL}/api/states",
            headers=HEADERS,
            timeout=3,
            verify=False
        )
        r.raise_for_status()
        return {s["entity_id"]: s for s in r.json()}
    except Exception:
        return {}

def is_on(ids, states):
    for e in (ids if isinstance(ids, list) else [ids]):
        st = states.get(e, {}).get("state")
        if st in ("on", "cool"):
            return True
    return False

# ============================================================
# LED / PAD CONTROL
# ============================================================

def set_pad(key, val, is_cc):
    if not outport:
        return
    try:
        if is_cc:
            msg = mido.Message("control_change", control=key, value=val)
        else:
            msg = mido.Message("note_on", note=key, velocity=val)
        outport.send(msg)
    except Exception:
        pass

def update_pads():
    global _last_update

    if time.time() - _last_update < 0.2:
        return
    _last_update = time.time()

    states = get_states()

    # room buttons (CC)
    for room in rooms:
        any_on = any(is_on(a["entity_ids"], states) for a in room["actions"])
        set_pad(
            room["room_key"],
            room.get("room_key_color_any_on", 9)
            if any_on else room.get("room_key_color_off", 5),
            True
        )

    # action pads (notes)
    for act in active_room["actions"]:
        ids = act["entity_ids"]
        on  = is_on(ids, states)
        set_pad(act["key"], act["on_color"] if on else act["off_color"], False)

    # clear unused grid (8x8)
    used = {r["room_key"] for r in rooms} | {a["key"] for a in active_room["actions"]}
    for k in range(64):
        if k not in used:
            set_pad(k, 0, False)

# ============================================================
# WEBSOCKET (REALTIME UPDATES)
# ============================================================

def _on_ws_message(ws, msg):
    try:
        d = json.loads(msg)
        if d.get("type") == "event":
            update_pads()
    except Exception:
        pass

def _on_ws_open(ws):
    ws.send(json.dumps({"type": "auth", "access_token": HASS_TOKEN}))
    ws.send(json.dumps({
        "id": 1,
        "type": "subscribe_events",
        "event_type": "state_changed"
    }))

def _start_ws():
    if PASSIVE_MODE:
        return
    ws_url = HASS_URL.replace("http", "ws") + "/api/websocket"
    while True:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=_on_ws_open,
                on_message=_on_ws_message
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            print("⚠️ WS reconnect:", e)
        time.sleep(5)

# ============================================================
# MAIN
# ============================================================

open_ports()

with open("config.json") as f:
    rooms = json.load(f).get("rooms", [])

if not rooms:
    print("❌ No rooms defined in config.json")
    sys.exit(1)

active_room = rooms[0]

threading.Thread(target=_start_ws, daemon=True).start()

mode_text = "PASSIVE MODE" if PASSIVE_MODE else "ACTIVE MODE"
print(f"🚀 Controller Started ({mode_text})")
update_pads()

last_health_check = 0

while True:
    try:
        # 🔍 health check every 1 second
        if time.time() - last_health_check > 1:
            last_health_check = time.time()
            if not ports_still_present():
                print("🔌 Launchpad disconnected, waiting to reconnect…")
                try:
                    if inport:
                        inport.close()
                    if outport:
                        outport.close()
                except Exception:
                    pass
                inport = outport = None
                open_ports()
                update_pads()

        if not inport:
            time.sleep(0.1)
            continue

        for msg in inport.iter_pending():
            # Room select (CC)
            if msg.type == "control_change":
                for r in rooms:
                    if r["room_key"] == msg.control:
                        active_room = r
                        update_pads()

            # Action trigger (NOTE)
            elif msg.type == "note_on" and msg.velocity > 0:
                states = get_states()
                for act in active_room["actions"]:
                    if msg.note == act["key"]:
                        ids = act["entity_ids"]
                        dom = ids[0].split(".")[0]

                        if len(ids) > 1:
                            svc = "turn_off" if is_on(ids, states) else "turn_on"
                            for e in ids:
                                call_ha(e.split(".")[0], svc, {"entity_id": e})
                        else:
                            call_ha(dom, "toggle", {"entity_id": ids[0]})

                        update_pads()

        time.sleep(0.02)

    except Exception as e:
        print("❌ MIDI error:", e)
        try:
            if inport:
                inport.close()
            if outport:
                outport.close()
        except Exception:
            pass
        inport = outport = None
        time.sleep(2)
        open_ports()
        update_pads()
