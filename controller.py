# launchpad_controller.py

import mido
import requests
import json
import time
import threading
import websocket
import urllib3
import os
from dotenv import load_dotenv

# === CONFIG ===
load_dotenv()
HASS_URL   = os.getenv("HASS_URL")
HASS_TOKEN = os.getenv("HASS_TOKEN")
HEADERS    = {
    "Authorization": f"Bearer {HASS_TOKEN}",
    "Content-Type":  "application/json"
}

# Disable SSL warnings (for self-signed certs)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Global MIDI ports
inport = None
outport = None

def open_ports():
    """Scan and open the Launchpad MIDI ports, retry every 2 seconds."""
    global inport, outport
    while True:
        ins  = mido.get_input_names()
        outs = mido.get_output_names()
        print("🔍 MIDI inputs:",  ins)
        print("🔍 MIDI outputs:", outs)

        # find any port name containing 'launchpad'
        in_name  = next((p for p in ins  if "launchpad" in p.lower()), None)
        out_name = next((p for p in outs if "launchpad" in p.lower()), None)

        if in_name and out_name:
            try:
                inport  = mido.open_input(in_name)
                outport = mido.open_output(out_name)
                print(f"✅ Connected to Launchpad: in={in_name}, out={out_name}")
                return
            except Exception as e:
                print("❌ Error opening ports:", e)

        print("🔄 Launchpad not found. Retrying in 2s…")
        time.sleep(2)

# attempt initial connection
open_ports()

# load config.json
with open("config.json") as f:
    rooms = json.load(f).get("rooms", [])
if not rooms:
    print("❌ No rooms in config.json")
    exit(1)
active_room = rooms[0]

# --- Home Assistant helpers with debug ---
def call_ha(domain, svc, data):
    print(f"[DEBUG] HA → {domain}/{svc} {data}")
    url = f"{HASS_URL}/api/services/{domain}/{svc}"
    try:
        r = requests.post(url,
                          headers=HEADERS,
                          json=data,
                          timeout=3,
                          verify=False)
        print(f"[DEBUG]   ← {r.status_code} {r.text}")
        if not r.ok:
            print(f"❌ HA error {r.status_code}: {r.text}")
    except Exception as e:
        print("❌ HA exception:", e)

def get_states():
    try:
        r = requests.get(f"{HASS_URL}/api/states",
                         headers=HEADERS,
                         timeout=3,
                         verify=False)
        r.raise_for_status()
        return {s["entity_id"]: s for s in r.json()}
    except Exception as e:
        print("❌ State fetch error:", e)
        return {}

def is_on(ids, states):
    for e in (ids if isinstance(ids, list) else [ids]):
        st = states.get(e, {}).get("state")
        dom = e.split(".")[0]
        if dom == "climate" and st == "cool":
            return True
        if st == "on":
            return True
    return False

# --- Launchpad LED control ---
def set_pad(key, val, is_cc):
    if outport is None: return
    msg = (mido.Message("control_change", control=key, value=val)
           if is_cc else
           mido.Message("note_on",      note=key, velocity=val))
    outport.send(msg)

def update_pads():
    states = get_states()
    # room selectors
    for room in rooms:
        any_on = any(is_on(a["entity_ids"], states) for a in room["actions"])
        col = room.get("room_key_color_any_on",9) if any_on else room.get("room_key_color_off",5)
        set_pad(room["room_key"], col, True)

    # action buttons
    for act in active_room["actions"]:
        key    = act["key"]
        ids    = act["entity_ids"]
        dom    = ids[0].split(".")[0]

        # custom service
        if "service" in act:
            call_ha(dom, act["service"], act["service_data"])
            color = act.get("on_color")
        # climate
        elif dom == "climate":
            st = states.get(ids[0],{}).get("state","")
            color = act.get("on_color") if st=="cool" else act.get("off_color")
        # brightness
        elif "brightness" in act:
            cur = states.get(ids[0],{}).get("attributes",{}).get("brightness",0)
            color = act.get("on_color") if cur>=act["brightness"] else act.get("off_color")
        # default on/off
        else:
            on_state = is_on(ids, states)
            color = act.get("on_color") if on_state else act.get("off_color")

        set_pad(key, color, False)

    # clear unused pads
    used = {r["room_key"] for r in rooms} | {a["key"] for a in active_room["actions"]}
    for k in range(128):
        if k not in used:
            set_pad(k,0,True)
            set_pad(k,0,False)

def switch_room(cc):
    global active_room
    for room in rooms:
        if room["room_key"] == cc:
            active_room = room
            update_pads()
            break

# --- WebSocket for realtime updates ---
WS_URL = HASS_URL.replace("http","ws") + "/api/websocket"
_ws_id = 1

def _on_ws_message(ws, msg):
    d = json.loads(msg)
    if d.get("type")=="event" and d["event"]["event_type"]=="state_changed":
        update_pads()

def _on_ws_open(ws):
    global _ws_id
    ws.send(json.dumps({"type":"auth","access_token":HASS_TOKEN}))
    ws.send(json.dumps({"id":_ws_id,"type":"subscribe_events","event_type":"state_changed"}))
    _ws_id += 1

def _start_ws():
    websocket.enableTrace(False)
    ws = websocket.WebSocketApp(WS_URL,
                                on_open=_on_ws_open,
                                on_message=_on_ws_message)
    ws.run_forever()

threading.Thread(target=_start_ws, daemon=True).start()

# --- MAIN LOOP with debug and auto-reconnect ---
print("🚀 Controller Started")
update_pads()

while True:
    # if unplugged, attempt reconnect
    if inport is None or outport is None:
        print("🔌 Launchpad disconnected, retrying…")
        open_ports()
        print("🔋 Reconnected, restoring LEDs…")
        update_pads()

    try:
        for msg in inport:
            print(f"[DEBUG] pad pressed: {msg}")
            if msg.type == "control_change":
                print(f"[DEBUG] switch room to CC={msg.control}")
                switch_room(msg.control)
            elif msg.type == "note_on" and msg.velocity > 0:
                print(f"[DEBUG] note_on received: note={msg.note}")
                states = get_states()
                for act in active_room["actions"]:
                    print(f"[DEBUG] checking action key={act['key']} entities={act['entity_ids']}")
                    if msg.note != act["key"]:
                        continue
                    print(f"[DEBUG] matched action: {act}")
                    ids = act["entity_ids"]
                    dom = ids[0].split(".")[0]

                    if "service" in act:
                        call_ha(dom, act["service"], act["service_data"])
                    elif dom == "climate":
                        eid, st = ids[0], states.get(ids[0],{}).get("state","")
                        svc = "turn_off" if st=="cool" else "set_hvac_mode"
                        data = {"entity_id": eid} if svc=="turn_off" else {"entity_id": eid, "hvac_mode": "cool"}
                        call_ha("climate", svc, data)
                    elif "brightness" in act:
                        for e in ids:
                            call_ha(dom, "turn_on", {"entity_id": e, "brightness": act["brightness"]})
                    else:
                        if len(ids) > 1:
                            svc = "turn_off" if is_on(ids, states) else "turn_on"
                            for e in ids:
                                call_ha(e.split(".")[0], svc, {"entity_id": e})
                        else:
                            call_ha(dom, "toggle", {"entity_id": ids[0]})

                    time.sleep(0.1)
                    update_pads()
                    break
    except Exception as e:
        print("❌ MIDI error, reconnecting…", e)
        inport = outport = None
        time.sleep(1)
