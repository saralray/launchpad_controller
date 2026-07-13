# 🎹 Launchpad Controller (Passive MIDI Daemon)

A **stable Linux MIDI daemon** that connects a  
**Novation Launchpad Mini MK3** to **Home Assistant**.

Designed for **USB re-plug safety**, **systemd**, and **real-world reliability**.

---

## ✨ Features

- 🎛 Control Home Assistant from Launchpad
- 🔌 Auto-start when Launchpad is plugged in (udev)
- 🔁 Safe USB re-plug (no crash, no restart loop)
- 💤 Passive daemon mode
  - Unplug → service stays alive
  - Re-plug → auto reconnect
- 🕒 Startup delay (USB / ALSA settle)
- 🔐 Optional `.env` (safe for GitHub)
- ⚙️ Managed by systemd
- 🧠 No USB `BindsTo=` (avoids re-enumeration bugs)

---

## 📁 Project Structure

```
launchpad_controller/
├── controller.py          # entry shim → launchpad.app:main
├── launchpad/             # package
│   ├── app.py             # Controller + main loop
│   ├── config.py          # typed config model (dataclasses) + save
│   ├── ha_client.py       # HAClient: state cache, REST, WebSocket
│   ├── midi.py            # MidiSurface: ports + LED output
│   ├── presets_api.py     # PresetHA façade for presets
│   ├── manage.py          # Tkinter macro editor (python -m launchpad.manage)
│   └── palette.py         # velocity → RGB for GUI swatches
├── presets/               # run(ha) modules (all_toggle, wave, chaos)
├── config.json
├── requirements.txt
├── install-ubuntu.sh
├── install-fedora.sh
└── README.md
```

---

## 🔐 Environment Variables

Create `.env` (do NOT commit):

```
HASS_URL=https://homeassistant.local:8123
HASS_TOKEN=LONG_LIVED_ACCESS_TOKEN
```

If `.env` is missing, the controller runs in **PASSIVE MODE**
(no Home Assistant calls).

---

## 🎛 config.json

Defines how Launchpad buttons map to Home Assistant entities.

- `room_key` → control_change (top buttons)
- `key` → note_on (grid)

---

## 🎹 Key Checker (Find Button Numbers)

Before editing `config.json`, you need to know **which Launchpad button sends which MIDI value**.

Launchpad buttons send raw MIDI messages such as:

```
note_on note=0 velocity=127
control_change control=98 value=0
```

---

### ▶️ How to Check Keys

Create and run this script:

```python
import mido

port = next((p for p in mido.get_input_names() if "launchpad" in p.lower()), None)

if not port:
    print("Launchpad not found")
    exit(1)

print("Listening on:", port)

with mido.open_input(port) as inp:
    for msg in inp:
        print(msg)
```

Run:

```
python keychecker.py
```

---

### 🧾 Mapping Summary

| MIDI Message | Use In config.json |
|-------------|--------------------|
| note_on note=X | actions[].key |
| control_change control=X | room_key |

---

## 🖥️ Macro Manager (GUI)

Edit rooms, macros, and colors without hand-editing `config.json`:

```
sudo systemctl stop launchpad_controller   # free the MIDI port
python -m launchpad.manage
```

- **9x9 grid preview** of the selected room.
- **Learn mode** — click *Learn*, press a physical Launchpad button, its
  note/CC number is captured automatically (built-in key checker).
- **Entity picker** — Home Assistant entities are fetched via `.env`
  (free-text entry in passive mode).
- **Color test** — preview a color live on the device.

Needs Tkinter: `sudo apt install python3-tk`. Saves to `config.json` on disk —
restart the daemon to apply:

```
sudo systemctl restart launchpad_controller
```

---

## ⚙️ Installation

```
chmod +x install.sh
sudo ./install.sh
```

---

## 🪵 Logs

```
journalctl -u launchpad_controller -f
```

---

## 📜 License

MIT License
