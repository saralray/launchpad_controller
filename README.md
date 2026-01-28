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
├── controller.py
├── config.json
├── requirements.txt
├── install.sh
├── .env.example
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
