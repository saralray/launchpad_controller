"""Desktop app to edit config.json (rooms / macros / colors) for the
Launchpad controller.

Run:
    python -m launchpad.manage

Features:
- Visual 9x9 grid preview of the selected room, drawn to mirror the physical
  device: round function/scene buttons, square pads, lit pads glowing their
  real velocity color.
- Learn mode: click Learn, press a physical Launchpad button, the note/CC
  number is captured. Requires the daemon stopped so this app can hold the
  MIDI port:  sudo systemctl stop launchpad_controller
- Map layout: calibration wizard (Map layout button) that steps through every
  grid position and records which physical button sits there, so the grid
  matches your unit's actual note/CC numbering. Saved to layout.json.
- Home Assistant entity picker: entities are fetched via .env credentials
  (falls back to free-text entry in passive mode).
- Color fields can be previewed live on the device.

This app never runs while the daemon owns the MIDI port; it edits config.json
on disk. Saving restarts the systemd daemon automatically so the changes take
effect (via systemctl, with a pkexec fallback for the privilege prompt).
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
from pathlib import Path

from . import device
from .config import Action, Config, Room, load_config, save_config
from .ha_client import HAClient
from .layout import Layout, load_layout, save_layout
from .palette import hex_color, mix, rgb, to_hex
from .settings import get_credentials, load_settings, save_settings

try:
    import mido
except Exception:  # pragma: no cover - optional at edit time
    mido = None

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ImportError:
    raise SystemExit(
        "Tkinter is required for the manage GUI but is not installed.\n"
        "  Ubuntu/Debian:  sudo apt install python3-tk\n"
        "  Fedora:         sudo dnf install python3-tkinter\n"
        "A venv built before installing it picks it up automatically once "
        "the system package is present (re-run the installer to rebuild the "
        "service venv)."
    )

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
PRESETS_DIR = PROJECT_ROOT / "presets"
ICON_PATH = PROJECT_ROOT / "assets" / "launchpad.png"

SERVICE_NAME = "launchpad_controller"

GRID = 9  # 9x9 launchpad

# ======================================================================
# design tokens — "Chassis": the app as an extension of the hardware.
# The pad velocity colors are the only chroma; everything else is the
# matte-black body. Selection/focus is a plain white ring.
# ======================================================================

CHASSIS = "#0E0F13"
CHASSIS_RGB = (14, 15, 19)
PANEL = "#171A21"
PANEL2 = "#1F232C"  # raised controls
WELL = "#13161C"    # dark pad well / input field
BEZEL = "#2B323E"
INK = "#E7EAF0"
INK_DIM = "#828B9B"
SELECT = "#FFFFFF"
LIVE = "#18D45B"    # "powered" green — save action + connected LED
AMBER = "#FFB020"
WHITE = (255, 255, 255)

FONT_MONO = ("DejaVu Sans Mono", 10)
FONT_PAD = ("DejaVu Sans Mono", 9)
FONT_EYE = ("DejaVu Sans", 8, "bold")
FONT_BODY = ("DejaVu Sans", 10)
FONT_H = ("DejaVu Sans", 13, "bold")


def _lum(c: tuple[int, int, int]) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


# Grid geometry lives in launchpad/layout.py: a `Layout` maps note/CC
# numbers to (row, col) cells, either from the documented formula or from
# a calibration the user recorded with the "Map layout" wizard. The app
# holds one `self.layout` instance and routes all placement through it.


# ======================================================================
# PadGrid: the signature element — a canvas that renders the device
# ======================================================================

class PadGrid(tk.Canvas):
    CELL = 46
    GAP = 7
    MARGIN = 16

    def __init__(self, master, on_click):
        span = self.MARGIN * 2 + GRID * self.CELL + (GRID - 1) * self.GAP
        super().__init__(
            master, width=span, height=span, bg=CHASSIS, highlightthickness=0, bd=0
        )
        self.on_click = on_click
        self._rects: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        self.bind("<Button-1>", self._click)

    def _box(self, r: int, c: int) -> tuple[int, int, int, int]:
        x0 = self.MARGIN + c * (self.CELL + self.GAP)
        y0 = self.MARGIN + r * (self.CELL + self.GAP)
        return x0, y0, x0 + self.CELL, y0 + self.CELL

    def _click(self, ev) -> None:
        for (r, c), (x0, y0, x1, y1) in self._rects.items():
            if x0 <= ev.x <= x1 and y0 <= ev.y <= y1:
                self.on_click(r, c)
                return

    def render(self, pads: dict, selected: tuple[int, int] | None) -> None:
        self.delete("all")
        self._rects = {}
        for r in range(GRID):
            for c in range(GRID):
                self._rects[(r, c)] = self._box(r, c)
                self._draw(r, c, pads.get((r, c)), selected == (r, c))

    def _shape(self, x0, y0, x1, y1, round_btn, **kw):
        # round function/scene buttons vs square grid pads — mirrors hardware
        if round_btn:
            return self.create_oval(x0, y0, x1, y1, **kw)
        rad = 11
        pts = [
            x0 + rad, y0, x1 - rad, y0, x1, y0, x1, y0 + rad,
            x1, y1 - rad, x1, y1, x1 - rad, y1, x0 + rad, y1,
            x0, y1, x0, y1 - rad, x0, y0 + rad, x0, y0,
        ]
        return self.create_polygon(pts, smooth=True, **kw)

    def _draw(self, r, c, info, sel) -> None:
        x0, y0, x1, y1 = self._box(r, c)
        round_btn = r == 0 or c == 8
        lit = info is not None and info[1] is not None

        self._shape(x0, y0, x1, y1, round_btn, fill=WELL, outline=BEZEL, width=1)

        if lit:
            color = rgb(info[1])
            halo = to_hex(mix(color, CHASSIS_RGB, 0.62))
            self._shape(x0 - 3, y0 - 3, x1 + 3, y1 + 3, round_btn,
                        fill="", outline=halo, width=3)
            self._shape(x0, y0, x1, y1, round_btn, fill=to_hex(color),
                        outline=to_hex(mix(color, WHITE, 0.3)), width=1)

        if info is not None:
            tcol = ("#0B0D10" if lit and _lum(rgb(info[1])) > 140 else
                    (INK if lit else INK_DIM))
            self.create_text((x0 + x1) // 2, (y0 + y1) // 2,
                             text=info[2], fill=tcol, font=FONT_PAD)

        if sel:
            self._shape(x0 - 2, y0 - 2, x1 + 2, y1 + 2, round_btn,
                        fill="", outline=SELECT, width=2)


# ======================================================================
# MIDI bridge: reads the Launchpad in a thread, delivers to the GUI
# ======================================================================

class MidiBridge:
    def __init__(self):
        self.inport = None
        self.outport = None
        self.in_name = None
        self.status = "mido not installed" if mido is None else "not connected"
        self.events: "queue.Queue[tuple[str, int]]" = queue.Queue()
        self._stop = threading.Event()
        # No connect here — the GUI probes in a background thread after the
        # window is up, so a missing/busy device never blocks startup.

    def connect(self) -> None:
        if mido is None:
            return
        try:
            ins = mido.get_input_names()
            outs = mido.get_output_names()
            in_name = device.pick_launchpad_port(ins)
            out_name = device.pick_launchpad_port(outs)
            if not in_name:
                self.status = "Launchpad not found"
                return
            self.inport = mido.open_input(in_name)
            if out_name:
                self.outport = mido.open_output(out_name)
                # no layout is forced — Learn/Map read the device's real
                # note/CC numbers, exactly as the daemon and keychecker see them
            self.in_name = in_name
            self.status = f"connected: {in_name}"
            threading.Thread(target=self._loop, daemon=True).start()
        except Exception as e:
            self.status = f"port busy (stop the daemon?): {e}"

    def _loop(self) -> None:
        for msg in self.inport:
            if self._stop.is_set():
                return
            if msg.type == "note_on" and msg.velocity > 0:
                self.events.put(("note", msg.note))
            elif msg.type == "control_change" and msg.value > 0:
                self.events.put(("cc", msg.control))

    def light(self, number: int, color: int, is_cc: bool) -> None:
        if not self.outport:
            return
        try:
            self.outport.send(
                mido.Message("control_change", control=number, value=color)
                if is_cc
                else mido.Message("note_on", note=number, velocity=color)
            )
        except Exception:
            pass

    def close(self) -> None:
        self._stop.set()
        for p in (self.inport, self.outport):
            try:
                if p:
                    p.close()
            except Exception:
                pass


# ======================================================================
# GUI
# ======================================================================

class ManageApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Launchpad Macro Manager")
        self.geometry("1200x780")
        self.configure(bg=CHASSIS)
        self.minsize(1040, 680)
        self._set_app_icon()

        self.config_model: Config = load_config(CONFIG_PATH)
        self.layout: Layout = load_layout()
        self.midi = MidiBridge()
        self.entities: list[str] = []
        self.learn_target = None  # tk.Entry awaiting a captured number
        self.map_capture = None  # callback(kind, number) for the layout wizard
        self.current_room: Room | None = None
        self.current_action: Action | None = None

        self._setup_style()
        self._build_ui()
        self._load_entities_async()
        self._refresh_rooms()
        self._poll_midi()
        self._connect_async()  # probe MIDI without blocking the window
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_app_icon(self) -> None:
        # Tk 8.6 reads PNG natively; keep a ref so it isn't garbage-collected.
        try:
            self._icon_img = tk.PhotoImage(file=str(ICON_PATH))
            self.iconphoto(True, self._icon_img)
        except Exception:
            pass  # missing/unsupported icon must never block the GUI

    # ---- theming -------------------------------------------------------

    def _setup_style(self) -> None:
        st = ttk.Style()
        st.theme_use("clam")
        st.configure(".", background=PANEL, foreground=INK, font=FONT_BODY,
                     bordercolor=BEZEL, focuscolor=BEZEL)
        st.configure("TButton", background=PANEL2, foreground=INK, relief="flat",
                     padding=(11, 7), bordercolor=BEZEL, font=FONT_BODY)
        st.map("TButton",
               background=[("active", BEZEL), ("pressed", BEZEL)],
               foreground=[("disabled", INK_DIM)])
        st.configure("Live.TButton", background=LIVE, foreground="#07130B")
        st.map("Live.TButton", background=[("active", "#25E56C")])
        st.configure("Ghost.TButton", background=PANEL, foreground=INK_DIM)
        st.map("Ghost.TButton", background=[("active", PANEL2)])
        for w in ("TEntry", "TSpinbox"):
            st.configure(w, fieldbackground=WELL, foreground=INK, insertcolor=INK,
                         bordercolor=BEZEL, arrowcolor=INK_DIM, relief="flat",
                         padding=4)
        st.configure("TCombobox", fieldbackground=WELL, background=PANEL2,
                     foreground=INK, arrowcolor=INK_DIM, bordercolor=BEZEL,
                     relief="flat", padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", WELL)])
        st.configure("TCheckbutton", background=PANEL, foreground=INK_DIM,
                     indicatorcolor=WELL, focuscolor=BEZEL)
        st.map("TCheckbutton", background=[("active", PANEL)],
               indicatorcolor=[("selected", LIVE)])
        self.option_add("*TCombobox*Listbox.background", WELL)
        self.option_add("*TCombobox*Listbox.foreground", INK)
        self.option_add("*TCombobox*Listbox.selectBackground", BEZEL)
        self.option_add("*TCombobox*Listbox.selectForeground", INK)
        self.option_add("*TCombobox*Listbox.font", FONT_MONO)

    def _eyebrow(self, parent, text) -> tk.Label:
        return tk.Label(parent, text=text.upper(), fg=INK_DIM, bg=parent["bg"],
                        font=FONT_EYE, anchor="w")

    def _panel(self, parent) -> tk.Frame:
        return tk.Frame(parent, bg=PANEL, highlightbackground=BEZEL,
                        highlightthickness=1, bd=0)

    def _listbox(self, parent, **kw) -> tk.Listbox:
        return tk.Listbox(parent, bg=WELL, fg=INK, font=FONT_MONO,
                          selectbackground=BEZEL, selectforeground=INK,
                          highlightthickness=0, bd=0, activestyle="none",
                          relief="flat", **kw)

    # ---- layout --------------------------------------------------------

    def _build_ui(self) -> None:
        # --- top bar: identity lockup + status + actions ---
        top = tk.Frame(self, bg=CHASSIS)
        top.pack(fill="x", padx=18, pady=(16, 10))

        ident = tk.Frame(top, bg=CHASSIS)
        ident.pack(side="left")
        tk.Label(ident, text="NOVATION LAUNCHPAD MINI MK3", fg=INK_DIM, bg=CHASSIS,
                 font=FONT_EYE).pack(anchor="w")
        tk.Label(ident, text="Macro Manager", fg=INK, bg=CHASSIS,
                 font=("DejaVu Sans", 17, "bold")).pack(anchor="w")

        actions = tk.Frame(top, bg=CHASSIS)
        actions.pack(side="right")
        ttk.Button(actions, text="Save config", style="Live.TButton",
                   command=self._save).pack(side="right")
        ttk.Button(actions, text="Download JSON", style="Ghost.TButton",
                   command=self._export).pack(side="right", padx=(8, 0))
        ttk.Button(actions, text="Reload", style="Ghost.TButton",
                   command=self._reload).pack(side="right", padx=8)
        ttk.Button(actions, text="Connection", style="Ghost.TButton",
                   command=self._open_connection).pack(side="right")

        status = tk.Frame(top, bg=CHASSIS)
        status.pack(side="right", padx=(0, 24))
        self.led = tk.Canvas(status, width=12, height=12, bg=CHASSIS,
                             highlightthickness=0)
        self.led.pack(side="left", pady=2)
        self._led_dot = self.led.create_oval(1, 1, 11, 11, fill=INK_DIM, outline="")
        self.status_var = tk.StringVar(value=self.midi.status)
        tk.Label(status, textvariable=self.status_var, fg=INK_DIM, bg=CHASSIS,
                 font=FONT_MONO).pack(side="left", padx=8)
        self._reconnect_btn = ttk.Button(status, text="Reconnect",
                                         style="Ghost.TButton", command=self._reconnect)
        self._reconnect_btn.pack(side="left")
        self._update_led()

        body = tk.Frame(self, bg=CHASSIS)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        self._build_rooms(body)
        self._build_grid(body)
        self._build_editor(body)

    def _build_rooms(self, body) -> None:
        panel = self._panel(body)
        panel.pack(side="left", fill="y")
        inner = tk.Frame(panel, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=14, pady=14)

        self._eyebrow(inner, "Rooms / Scenes").pack(fill="x")
        self.rooms_list = self._listbox(inner, width=22)
        self.rooms_list.pack(fill="y", expand=True, pady=(8, 8))
        self.rooms_list.bind("<<ListboxSelect>>", lambda e: self._on_room_select())

        rb = tk.Frame(inner, bg=PANEL)
        rb.pack(fill="x")
        ttk.Button(rb, text="Add", width=6, command=self._add_room).pack(side="left")
        ttk.Button(rb, text="Rename", width=8, style="Ghost.TButton",
                   command=self._rename_room).pack(side="left", padx=4)
        ttk.Button(rb, text="Delete", width=7, style="Ghost.TButton",
                   command=self._del_room).pack(side="left")

        self._eyebrow(inner, "Selector button (CC)").pack(fill="x", pady=(16, 4))
        rk = tk.Frame(inner, bg=PANEL)
        rk.pack(fill="x")
        self.room_key_var = tk.StringVar()
        e = ttk.Entry(rk, textvariable=self.room_key_var, width=6, font=FONT_MONO)
        e.pack(side="left")
        ttk.Button(rk, text="Learn", width=7, command=lambda: self._learn(e)).pack(
            side="left", padx=6
        )
        self.room_key_var.trace_add("write", lambda *a: self._on_room_key_edit())

    def _build_grid(self, body) -> None:
        panel = self._panel(body)
        panel.pack(side="left", fill="both", expand=True, padx=14)
        inner = tk.Frame(panel, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=14, pady=14)

        head = tk.Frame(inner, bg=PANEL)
        head.pack(fill="x")
        self._eyebrow(head, "Pad grid").pack(side="left")
        self.grid_room_var = tk.StringVar()
        tk.Label(head, textvariable=self.grid_room_var, fg=INK, bg=PANEL,
                 font=FONT_H).pack(side="left", padx=10)
        ttk.Button(head, text="Map layout", style="Ghost.TButton",
                   command=self._map_layout).pack(side="right")

        wrap = tk.Frame(inner, bg=PANEL)
        wrap.pack(expand=True)
        self.pad_grid = PadGrid(wrap, self._on_cell)
        self.pad_grid.pack(pady=10)

        tk.Label(inner, text="Click a lit pad to edit its macro · an empty pad to "
                 "add one · press Learn then a physical button to capture",
                 fg=INK_DIM, bg=PANEL, font=("DejaVu Sans", 9),
                 wraplength=460, justify="left").pack(fill="x")

        self._eyebrow(inner, "Unplaced macros").pack(fill="x", pady=(14, 4))
        self.unplaced = self._listbox(inner, height=3)
        self.unplaced.pack(fill="x")
        self.unplaced.bind("<<ListboxSelect>>", lambda e: self._on_unplaced())

    def _build_editor(self, body) -> None:
        panel = self._panel(body)
        panel.pack(side="left", fill="y")
        parent = tk.Frame(panel, bg=PANEL)
        parent.pack(fill="both", expand=True, padx=16, pady=14)

        self._eyebrow(parent, "Macro").pack(fill="x", pady=(0, 8))

        self._eyebrow(parent, "Pad (note)").pack(fill="x")
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=(2, 10))
        self.key_var = tk.StringVar()
        ke = ttk.Entry(row, textvariable=self.key_var, width=7, font=FONT_MONO)
        ke.pack(side="left")
        ttk.Button(row, text="Learn", width=7, command=lambda: self._learn(ke)).pack(
            side="left", padx=6
        )

        self._eyebrow(parent, "Type").pack(fill="x")
        self.type_var = tk.StringVar(value="entity")
        ttk.Combobox(parent, textvariable=self.type_var, values=["entity", "preset"],
                     width=12, state="readonly").pack(fill="x", pady=(2, 10))
        self.type_var.trace_add("write", lambda *a: self._sync_type_fields())

        # entity/preset fields live here so they stay above Colors + buttons
        self.type_body = tk.Frame(parent, bg=PANEL)
        self.type_body.pack(fill="x")

        # entity fields
        self.entity_frame = tk.Frame(self.type_body, bg=PANEL)
        self._eyebrow(self.entity_frame, "Entities").pack(fill="x")
        self.entities_list = self._listbox(self.entity_frame, height=6, width=32)
        self.entities_list.pack(fill="x", pady=(2, 4))
        erow = tk.Frame(self.entity_frame, bg=PANEL)
        erow.pack(fill="x")
        self.entity_pick = ttk.Combobox(erow, width=24, font=FONT_MONO)
        self.entity_pick.pack(side="left", fill="x", expand=True)
        ttk.Button(erow, text="+", width=3, command=self._add_entity).pack(
            side="left", padx=(6, 2))
        ttk.Button(erow, text="−", width=3, style="Ghost.TButton",
                   command=self._remove_entity).pack(side="left")

        # preset field
        self.preset_frame = tk.Frame(self.type_body, bg=PANEL)
        self._eyebrow(self.preset_frame, "Preset").pack(fill="x")
        self.preset_var = tk.StringVar()
        self.preset_pick = ttk.Combobox(
            self.preset_frame, textvariable=self.preset_var,
            values=self._scan_presets(), width=18, state="readonly")
        self.preset_pick.pack(fill="x", pady=2)

        # colors
        self._eyebrow(parent, "Colors").pack(fill="x", pady=(12, 2))
        crow = tk.Frame(parent, bg=PANEL)
        crow.pack(fill="x")
        self.on_color_var = tk.IntVar(value=21)
        self.off_color_var = tk.IntVar(value=5)
        self._color_widget(crow, "On", self.on_color_var)
        self._color_widget(crow, "Off", self.off_color_var)

        brow = tk.Frame(parent, bg=PANEL)
        brow.pack(fill="x", pady=(16, 0))
        ttk.Button(brow, text="Apply", command=self._apply_action).pack(
            side="left", fill="x", expand=True)
        ttk.Button(brow, text="Delete", width=8, style="Ghost.TButton",
                   command=self._delete_action).pack(side="left", padx=(8, 0))
        self._sync_type_fields()

    def _color_widget(self, parent, label, var) -> None:
        f = tk.Frame(parent, bg=PANEL)
        f.pack(fill="x", pady=3)
        tk.Label(f, text=label, fg=INK_DIM, bg=PANEL, font=FONT_EYE,
                 width=4, anchor="w").pack(side="left")
        chip = tk.Canvas(f, width=52, height=26, bg=PANEL, highlightthickness=0,
                         cursor="hand2")
        chip.pack(side="left", padx=(0, 8))
        chip.bind("<Button-1>", lambda _e: self._pick_color(var))

        def paint(*_):
            chip.delete("all")
            col = rgb(var.get())
            chip.create_rectangle(1, 1, 50, 24, fill=to_hex(col),
                                  outline=to_hex(mix(col, WHITE, 0.3)))
            chip.create_text(25, 12, text=str(var.get()),
                             fill="#0B0D10" if _lum(col) > 140 else INK,
                             font=FONT_PAD)

        ttk.Button(f, text="Pick", width=5, style="Ghost.TButton",
                   command=lambda: self._pick_color(var)).pack(side="left", padx=(6, 0))
        ttk.Button(f, text="Test", width=5, style="Ghost.TButton",
                   command=lambda: self._test_color(var)).pack(side="left", padx=(6, 0))
        var.trace_add("write", paint)
        paint()

    # ---- data helpers --------------------------------------------------

    def _scan_presets(self) -> list[str]:
        if not PRESETS_DIR.is_dir():
            return []
        return sorted(
            p.stem
            for p in PRESETS_DIR.glob("*.py")
            if p.stem != "__init__"
        )

    def _load_entities_async(self) -> None:
        def work():
            url, token = get_credentials()
            ha = HAClient(url, token)
            if ha.passive:
                return
            states = ha.refresh_states(force=True)
            self.entities = sorted(states.keys())
            self.after(0, self._apply_entities)

        threading.Thread(target=work, daemon=True).start()

    def _apply_entities(self) -> None:
        self.entity_pick.configure(values=self.entities)

    # ---- rooms ---------------------------------------------------------

    def _refresh_rooms(self) -> None:
        self.rooms_list.delete(0, "end")
        for r in self.config_model.rooms:
            self.rooms_list.insert("end", f"{r.name}   CC {r.room_key}")
        if self.config_model.rooms:
            self.rooms_list.selection_set(0)
            self._on_room_select()

    def _selected_room_index(self) -> int | None:
        sel = self.rooms_list.curselection()
        return sel[0] if sel else None

    def _on_room_select(self) -> None:
        idx = self._selected_room_index()
        if idx is None:
            return
        self.current_room = self.config_model.rooms[idx]
        self.current_action = None
        self.grid_room_var.set(self.current_room.name)
        self.room_key_var.set(str(self.current_room.room_key))
        self._refresh_grid()
        self._clear_editor()

    def _on_room_key_edit(self) -> None:
        if not self.current_room:
            return
        try:
            self.current_room.room_key = int(self.room_key_var.get())
            self._refresh_grid()
        except ValueError:
            pass

    def _add_room(self) -> None:
        name = simpledialog.askstring("New room", "Room name:", parent=self)
        if not name:
            return
        self.config_model.rooms.append(Room(name=name, room_key=0))
        self._refresh_rooms()
        self.rooms_list.selection_clear(0, "end")
        self.rooms_list.selection_set("end")
        self._on_room_select()

    def _rename_room(self) -> None:
        if not self.current_room:
            return
        name = simpledialog.askstring(
            "Rename", "Room name:", initialvalue=self.current_room.name, parent=self
        )
        if name:
            self.current_room.name = name
            idx = self._selected_room_index()
            self._refresh_rooms()
            if idx is not None:
                self.rooms_list.selection_set(idx)

    def _del_room(self) -> None:
        idx = self._selected_room_index()
        if idx is None:
            return
        if messagebox.askyesno("Delete room", "Delete this room?"):
            del self.config_model.rooms[idx]
            self._refresh_rooms()

    # ---- grid ----------------------------------------------------------

    def _refresh_grid(self) -> None:
        self.unplaced.delete(0, "end")
        self._unplaced_actions: list[Action] = []
        pads: dict[tuple[int, int], tuple[str, int | None, str]] = {}
        if not self.current_room:
            self.pad_grid.render(pads, None)
            return

        # room selectors across all rooms give spatial context; the active
        # room's own selector glows brighter so you can place yourself
        for room in self.config_model.rooms:
            cell = self.layout.cell_for_number(room.room_key, is_cc=True)
            if cell:
                color = (room.room_key_color_any_on if room is self.current_room
                         else room.room_key_color_off)
                pads[cell] = ("selector", color, "RM")

        for act in self.current_room.actions:
            cell = self.layout.cell_for_number(act.key)
            label = act.preset[:4] if act.is_preset else str(act.key)
            if cell:
                pads[cell] = ("macro", act.on_color, label)
            else:
                self._unplaced_actions.append(act)
                self.unplaced.insert("end", f"{act.key}  {label}")

        selected = (self.layout.cell_for_number(self.current_action.key)
                    if self.current_action else None)
        self.pad_grid.render(pads, selected)

    def _on_cell(self, r: int, c: int) -> None:
        if not self.current_room:
            return
        number = self.layout.number_for_cell(r, c)
        act = next(
            (a for a in self.current_room.actions
             if self.layout.cell_for_number(a.key) == (r, c)),
            None,
        )
        if act is None:
            if number is None:
                return
            if not messagebox.askyesno("New macro", f"Add a macro on pad {number}?"):
                return
            act = Action(key=number, on_color=21, off_color=5, entity_ids=[])
            self.current_room.actions.append(act)
        self._edit_action(act)

    def _on_unplaced(self) -> None:
        sel = self.unplaced.curselection()
        if sel and sel[0] < len(self._unplaced_actions):
            self._edit_action(self._unplaced_actions[sel[0]])

    # ---- action editor -------------------------------------------------

    def _clear_editor(self) -> None:
        self.current_action = None
        self.key_var.set("")
        self.type_var.set("entity")
        self.entities_list.delete(0, "end")
        self.preset_var.set("")
        self.on_color_var.set(21)
        self.off_color_var.set(5)
        self._refresh_grid()

    def _edit_action(self, act: Action) -> None:
        self.current_action = act
        self.key_var.set(str(act.key))
        self.type_var.set("preset" if act.is_preset else "entity")
        self.entities_list.delete(0, "end")
        for e in act.entity_ids or []:
            self.entities_list.insert("end", e)
        self.preset_var.set(act.preset or "")
        self.on_color_var.set(act.on_color)
        self.off_color_var.set(act.off_color)
        self._sync_type_fields()
        self._refresh_grid()

    def _sync_type_fields(self) -> None:
        if self.type_var.get() == "preset":
            self.entity_frame.pack_forget()
            self.preset_frame.pack(fill="x", pady=2)
        else:
            self.preset_frame.pack_forget()
            self.entity_frame.pack(fill="x", pady=2)

    def _add_entity(self) -> None:
        val = self.entity_pick.get().strip()
        if val:
            self.entities_list.insert("end", val)

    def _remove_entity(self) -> None:
        sel = self.entities_list.curselection()
        if sel:
            self.entities_list.delete(sel[0])

    def _apply_action(self) -> None:
        if not self.current_action:
            messagebox.showinfo("No macro", "Select or create a macro first.")
            return
        try:
            self.current_action.key = int(self.key_var.get())
        except ValueError:
            messagebox.showerror("Bad pad", "Pad number must be an integer.")
            return
        self.current_action.on_color = self.on_color_var.get()
        self.current_action.off_color = self.off_color_var.get()
        if self.type_var.get() == "preset":
            self.current_action.preset = self.preset_var.get() or None
            self.current_action.entity_ids = None
        else:
            self.current_action.preset = None
            self.current_action.entity_ids = list(self.entities_list.get(0, "end"))
        self._refresh_grid()

    def _delete_action(self) -> None:
        if not (self.current_room and self.current_action):
            return
        if self.current_action in self.current_room.actions:
            self.current_room.actions.remove(self.current_action)
        self._clear_editor()

    # ---- learn / midi --------------------------------------------------

    def _learn(self, entry_widget) -> None:
        if self.midi.inport is None:
            messagebox.showwarning(
                "No MIDI",
                "Launchpad not connected. Stop the daemon first:\n"
                "sudo systemctl stop launchpad_controller",
            )
            return
        self.learn_target = entry_widget
        self.status_var.set("Learn: press a Launchpad button...")

    def _poll_midi(self) -> None:
        try:
            while True:
                kind, number = self.midi.events.get_nowait()
                if self.map_capture is not None:
                    self.map_capture(kind, number)
                elif self.learn_target is not None:
                    self.learn_target.delete(0, "end")
                    self.learn_target.insert(0, str(number))
                    self.learn_target = None
                    self.status_var.set(f"Captured {kind} {number}")
        except queue.Empty:
            pass
        self.after(50, self._poll_midi)

    def _map_layout(self) -> None:
        if self.midi.inport is None:
            messagebox.showwarning(
                "No MIDI",
                "Launchpad not connected. Stop the daemon first:\n"
                "sudo systemctl stop launchpad_controller",
            )
            return
        if self.learn_target is not None:
            self.learn_target = None
            self.status_var.set(self.midi.status)
        LayoutWizard(self)

    def _update_led(self) -> None:
        s = self.midi.status
        color = (LIVE if s.startswith("connected")
                 else AMBER if ("found" in s or "busy" in s)
                 else INK_DIM)
        self.led.itemconfigure(self._led_dot, fill=color)

    def _connect_async(self) -> None:
        if mido is None:
            self._update_led()
            return
        self.status_var.set("connecting...")

        def work():
            self.midi.connect()
            self.after(0, self._on_connect_done)

        threading.Thread(target=work, daemon=True).start()

    def _on_connect_done(self) -> None:
        self.status_var.set(self.midi.status)
        self._update_led()

    def _reconnect(self) -> None:
        self._connect_async()

    # ---- home assistant connection ------------------------------------

    def _open_connection(self) -> None:
        win = tk.Toplevel(self)
        win.title("Home Assistant connection")
        win.configure(bg=PANEL)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()

        frm = tk.Frame(win, bg=PANEL)
        frm.pack(fill="both", expand=True, padx=20, pady=18)

        saved = load_settings()
        url0, tok0 = get_credentials()

        tk.Label(frm, text="Configure the Home Assistant server so the app can "
                 "list entities and the daemon can control them. No .env needed.",
                 fg=INK_DIM, bg=PANEL, font=("DejaVu Sans", 9),
                 wraplength=360, justify="left").pack(fill="x", pady=(0, 12))

        self._eyebrow(frm, "Server URL").pack(fill="x")
        url_var = tk.StringVar(value=saved.get("hass_url") or url0 or "")
        ttk.Entry(frm, textvariable=url_var, width=44, font=FONT_MONO).pack(
            fill="x", pady=(2, 4))
        tk.Label(frm, text="e.g. https://homeassistant.local:8123", fg=INK_DIM,
                 bg=PANEL, font=("DejaVu Sans", 8)).pack(anchor="w", pady=(0, 10))

        self._eyebrow(frm, "Long-lived access token").pack(fill="x")
        tok_var = tk.StringVar(value=saved.get("hass_token") or tok0 or "")
        tok_entry = ttk.Entry(frm, textvariable=tok_var, width=44, show="•",
                              font=FONT_MONO)
        tok_entry.pack(fill="x", pady=(2, 4))
        show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frm, text="Show token", variable=show_var,
            command=lambda: tok_entry.configure(show="" if show_var.get() else "•"),
        ).pack(anchor="w")

        status = tk.Label(frm, text="", fg=INK_DIM, bg=PANEL, font=FONT_MONO,
                          anchor="w", justify="left", wraplength=360)
        status.pack(fill="x", pady=(12, 8))

        def test():
            u, t = url_var.get().strip(), tok_var.get().strip()
            status.configure(text="Testing...", fg=INK_DIM)

            def work():
                ha = HAClient(u or None, t or None)
                if ha.passive:
                    msg, col = "Enter both a URL and a token.", AMBER
                else:
                    n = len(ha.refresh_states(force=True))
                    if n:
                        msg, col = f"Connected — {n} entities found.", LIVE
                    else:
                        msg, col = "Reached server, but no entities (check token).", AMBER
                self.after(0, lambda: status.configure(text=msg, fg=col))

            threading.Thread(target=work, daemon=True).start()

        def save():
            save_settings({"hass_url": url_var.get().strip(),
                           "hass_token": tok_var.get().strip()})
            win.destroy()
            self._load_entities_async()

        btns = tk.Frame(frm, bg=PANEL)
        btns.pack(fill="x", pady=(4, 0))
        ttk.Button(btns, text="Save", style="Live.TButton", command=save).pack(
            side="right")
        ttk.Button(btns, text="Test", style="Ghost.TButton", command=test).pack(
            side="right", padx=8)
        ttk.Button(btns, text="Cancel", style="Ghost.TButton",
                   command=win.destroy).pack(side="right")

    def _pick_color(self, var) -> None:
        """Popup grid of all 128 Launchpad palette swatches; click to set var.

        Lights the pad live on click if the daemon is stopped (device held).
        """
        win = tk.Toplevel(self)
        win.title("Pick pad color")
        win.configure(bg=PANEL)
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()

        frm = tk.Frame(win, bg=PANEL)
        frm.pack(fill="both", expand=True, padx=14, pady=12)

        cols, cell, gap = 16, 26, 3
        cv = tk.Canvas(frm, bg=PANEL, highlightthickness=0,
                       width=cols * (cell + gap) + gap,
                       height=8 * (cell + gap) + gap)
        cv.pack()

        sel = {"v": var.get()}

        def draw():
            cv.delete("all")
            for i in range(128):
                r, c = divmod(i, cols)
                x0 = gap + c * (cell + gap)
                y0 = gap + r * (cell + gap)
                col = rgb(i)
                chosen = i == sel["v"]
                cv.create_rectangle(
                    x0, y0, x0 + cell, y0 + cell, fill=to_hex(col),
                    outline=SELECT if chosen else to_hex(mix(col, CHASSIS_RGB, 0.5)),
                    width=2 if chosen else 1)

        def click(e):
            c = int((e.x - gap) // (cell + gap))
            r = int((e.y - gap) // (cell + gap))
            i = r * cols + c
            if 0 <= c < cols and 0 <= i < 128:
                sel["v"] = i
                var.set(i)
                draw()
                self._test_color(var)

        cv.bind("<Button-1>", click)

        tk.Label(frm, text="Click a swatch — lights the pad live if the daemon "
                 "is stopped.", fg=INK_DIM, bg=PANEL,
                 font=("DejaVu Sans", 8)).pack(anchor="w", pady=(8, 0))

        btns = tk.Frame(frm, bg=PANEL)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Done", style="Live.TButton",
                   command=win.destroy).pack(side="right")
        draw()

    def _test_color(self, var) -> None:
        if not self.current_action:
            return
        self.midi.light(self.current_action.key, var.get(), False)

    # ---- persistence ---------------------------------------------------

    def _save(self) -> None:
        try:
            save_config(self.config_model, CONFIG_PATH)
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            return
        ok, detail = self._restart_service()
        if ok:
            messagebox.showinfo(
                "Saved",
                "config.json written and the daemon was restarted "
                "to apply the changes.",
            )
        else:
            messagebox.showwarning(
                "Saved (restart failed)",
                "config.json written, but the daemon could not be "
                f"restarted automatically:\n{detail}\n\n"
                "Restart it manually to apply:\n"
                f"sudo systemctl restart {SERVICE_NAME}",
            )

    def _restart_service(self) -> tuple[bool, str]:
        """Restart the systemd daemon so saved config takes effect.

        The manage GUI runs as the user while the daemon is a system
        service, so a plain ``systemctl restart`` only succeeds when the
        caller is root or already holds the polkit privilege. Fall back to
        ``pkexec`` for a graphical authentication prompt otherwise. Returns
        ``(ok, detail)`` where ``detail`` explains the failure.
        """
        if shutil.which("systemctl") is None:
            return False, "systemctl not found (service not installed?)"

        cmds = [["systemctl", "restart", SERVICE_NAME]]
        if shutil.which("pkexec") is not None:
            cmds.append(["pkexec", "systemctl", "restart", SERVICE_NAME])

        last = ""
        for cmd in cmds:
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=30
                )
            except Exception as e:  # e.g. pkexec dialog cancelled/missing
                last = str(e)
                continue
            if result.returncode == 0:
                return True, ""
            last = (result.stderr or result.stdout or "").strip() or (
                f"exit code {result.returncode}"
            )
        return False, last

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Download config as JSON",
            defaultextension=".json",
            initialfile="config.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w") as f:
                json.dump(self.config_model.to_dict(), f, indent=2)
        except Exception as e:
            messagebox.showerror("Download failed", str(e))
            return
        messagebox.showinfo("Downloaded", f"Config written to:\n{path}")

    def _reload(self) -> None:
        self.config_model = load_config(CONFIG_PATH)
        self._refresh_rooms()

    def _on_close(self) -> None:
        self.midi.close()
        self.destroy()


# ======================================================================
# LayoutWizard: calibrate which physical button sits at each grid cell
# ======================================================================

class LayoutWizard(tk.Toplevel):
    """Walk every grid position; the button pressed there is recorded.

    Starts from the app's current layout so re-running only touches cells
    you re-press. Skip leaves a cell as-is; clicking a cell jumps the
    target there so you can fix one position without a full pass.
    """

    MAP_COLOR = 21  # green swatch for an already-mapped cell

    def __init__(self, app: "ManageApp"):
        super().__init__(app)
        self.app = app
        self.title("Map layout")
        self.configure(bg=CHASSIS)
        self.transient(app)
        self.grab_set()

        self.work = Layout(app.layout.as_dict())  # edit a copy; commit on Finish
        # Skip the top bar (row 0, the CC function/selector row) — only the
        # 8x8 grid and right scene column get calibrated; unmapped cells fall
        # back to the documented formula.
        self.order = [(r, c) for r in range(1, GRID) for c in range(GRID)]
        self.idx = 0

        frm = tk.Frame(self, bg=CHASSIS)
        frm.pack(fill="both", expand=True, padx=18, pady=16)

        app._eyebrow(frm, "Calibrate layout").pack(fill="x")
        tk.Label(frm, text="Press the physical button that sits at the "
                 "highlighted position. The number it sends is recorded there.",
                 fg=INK_DIM, bg=CHASSIS, font=("DejaVu Sans", 9),
                 wraplength=460, justify="left").pack(fill="x", pady=(2, 10))

        self.grid_view = PadGrid(frm, self._on_cell_click)
        self.grid_view.pack()

        self.prompt = tk.StringVar()
        tk.Label(frm, textvariable=self.prompt, fg=INK, bg=CHASSIS,
                 font=FONT_MONO).pack(fill="x", pady=(10, 8))

        btns = tk.Frame(frm, bg=CHASSIS)
        btns.pack(fill="x")
        ttk.Button(btns, text="Finish & save", style="Live.TButton",
                   command=self._finish).pack(side="right")
        ttk.Button(btns, text="Skip", style="Ghost.TButton",
                   command=self._skip).pack(side="right", padx=8)
        ttk.Button(btns, text="Back", style="Ghost.TButton",
                   command=self._back).pack(side="right")
        ttk.Button(btns, text="Cancel", style="Ghost.TButton",
                   command=self._cancel).pack(side="left")

        app.map_capture = self._on_press
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._render()

    # ---- rendering -----------------------------------------------------

    def _render(self) -> None:
        pads: dict[tuple[int, int], tuple[str, int, str]] = {}
        for (r, c), (is_cc, num) in self.work.as_dict().items():
            label = f"c{num}" if is_cc else str(num)
            pads[(r, c)] = ("map", self.MAP_COLOR, label)
        target = self.order[self.idx] if self.idx < len(self.order) else None
        self.grid_view.render(pads, target)
        if target is None:
            self.prompt.set("All positions visited — Finish & save, or click a "
                            "cell to redo it.")
        else:
            r, c = target
            cur = self.work.number_for_cell(r, c)
            note = f"  (currently {cur})" if cur is not None else ""
            self.prompt.set(f"Position row {r}, col {c}  "
                            f"[{self.idx + 1}/{len(self.order)}]{note} — "
                            f"press its button")

    # ---- events --------------------------------------------------------

    def _on_press(self, kind: str, number: int) -> None:
        if self.idx >= len(self.order):
            return
        r, c = self.order[self.idx]
        is_cc = kind == "cc"
        self.work.set_cell(r, c, number, is_cc)
        self.app.midi.light(number, self.MAP_COLOR, is_cc)  # confirm blink
        self._advance()

    def _on_cell_click(self, r: int, c: int) -> None:
        if (r, c) in self.order:
            self.idx = self.order.index((r, c))
            self._render()

    def _advance(self) -> None:
        if self.idx < len(self.order):
            self.idx += 1
        self._render()

    def _skip(self) -> None:
        self._advance()

    def _back(self) -> None:
        if self.idx > 0:
            self.idx -= 1
        self._render()

    # ---- finish --------------------------------------------------------

    def _finish(self) -> None:
        try:
            save_layout(self.work)
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            return
        self.app.layout = self.work
        self._teardown()
        self.app._refresh_grid()
        self.app.status_var.set(f"Layout saved: {len(self.work.as_dict())} pads mapped")

    def _cancel(self) -> None:
        self._teardown()

    def _teardown(self) -> None:
        self.app.map_capture = None
        self.grab_release()
        self.destroy()


def main() -> None:
    ManageApp().mainloop()


if __name__ == "__main__":
    main()
