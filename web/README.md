# Launchpad Macro Manager — web dashboard

A browser control/status dashboard for the Launchpad → Home Assistant daemon. It
mirrors the desktop `python -m launchpad.manage` GUI (rooms · pad grid · macro
editor) with a refined, more polished visual design, and works as a **live
control surface**: click a pad to toggle its entities, and pad colors track
Home Assistant state in real time.

The UI is fully **dynamic** — it is not hardwired to one config. It adapts to
whatever rooms and entities a config defines, whether that's the bundled
`config.json`, a `config.json` served next to the app, or one you import in the
browser.

## Design

The layout was designed in Figma and implemented faithfully in React:
[Launchpad Macro Manager — Redesign](https://www.figma.com/design/FKrO5g0k5J7jA0Nx5e9wHj).

The "Chassis" design language matches the daemon's GUI — a matte near-black body
where the Launchpad velocity colors are the only chroma. `src/lib/palette.js`
and `src/lib/layout.js` are direct ports of the daemon's `launchpad/palette.py`
and the documented Mini MK3 X-Y grid geometry, so pads sit and glow exactly as
they do on the hardware.

## Run

```bash
cd web
npm install
npm run dev        # http://localhost:5173
npm run build      # production build to dist/
npm run preview    # serve the production build
```

## How it gets its data

1. **Config (rooms + macros).** On load the app tries to `fetch('./config.json')`
   served next to it; if that isn't present it falls back to the repo's bundled
   `config.json` (imported at build time). Use **Import** to load any other
   daemon-shaped `config.json`, or **Reload** to re-read, and **Download JSON**
   to export edits back to the daemon's format.

2. **Live state (entities).** Open **Connection** and enter your Home Assistant
   URL + a long-lived access token. The client (`src/lib/haClient.js`) is a
   browser analogue of the daemon's `launchpad/ha_client.py`: it polls
   `/api/states`, holds a persistent `state_changed` WebSocket subscription, and
   fires `turn_on` / `turn_off` service calls. Credentials are stored in the
   browser only.

3. **Demo mode.** With no credentials the dashboard runs in a self-contained
   demo: entity states are seeded deterministically from each entity id (so any
   config looks alive) and toggles update locally — the same PASSIVE_MODE
   contract the daemon uses.

## Layout

- **Rooms** — every room as a selector row with a live count of how many of its
  macros currently have an entity on (mirrors the daemon's room-select LED).
- **Pad grid** — the active room rendered as the 9×9 device: round function/scene
  buttons, square pads, lit pads glowing their on/off velocity color. Macros
  whose note doesn't fit the documented grid appear as **Unplaced** chips.
- **Macro editor** — the selected pad's entities with live state dots, on/off
  color swatches (with a full 128-swatch palette picker), and a toggle control.
