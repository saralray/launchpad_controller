"""Desktop app to edit config.json (rooms / macros / colors) for the
Launchpad controller.

Run:
    python -m launchpad.manage

Features:
- Visual 9x9 grid preview of the selected room.
- Learn mode: click Learn, press a physical Launchpad button, the note/CC
  number is captured. Requires the daemon stopped so this app can hold the
  MIDI port:  sudo systemctl stop launchpad_controller
- Home Assistant entity picker: entities are fetched via .env credentials
  (falls back to free-text entry in passive mode).
- Color fields can be previewed live on the device.

This app never runs while the daemon owns the MIDI port; it edits config.json
on disk. Restart the daemon after saving to apply changes.
"""

from __future__ import annotations

import os
import queue
import threading
from pathlib import Path

from dotenv import load_dotenv

from .config import Action, Config, Room, load_config, save_config
from .ha_client import HAClient
from .palette import hex_color

try:
    import mido
except Exception:  # pragma: no cover - optional at edit time
    mido = None

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
PRESETS_DIR = PROJECT_ROOT / "presets"

GRID = 9  # 9x9 launchpad


# ======================================================================
# grid geometry: map a note/CC number to a (row, col) cell, or None
# ======================================================================

def cell_for_number(number: int) -> tuple[int, int] | None:
    """Standard Launchpad Mini MK3 X-Y layout.

    Row 0 = top CC row (91-99). Col 8 = right-hand scene column (19..89).
    Main 8x8 grid = notes 11-88 (tens = row from bottom, ones = column).
    Numbers that don't fit return None (shown in the 'Unplaced' list).
    """
    if 91 <= number <= 99:
        return (0, number - 91)
    tens, ones = divmod(number, 10)
    if 1 <= tens <= 8 and ones == 9:  # right scene column
        return (9 - tens, 8)
    if 1 <= tens <= 8 and 1 <= ones <= 8:  # main grid
        return (9 - tens, ones - 1)
    return None


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
        if mido is not None:
            self.connect()

    def connect(self) -> None:
        if mido is None:
            return
        try:
            ins = mido.get_input_names()
            outs = mido.get_output_names()
            in_name = next(
                (p for p in ins if "launchpad" in p.lower() and "da" in p.lower()),
                None,
            )
            out_name = next((p for p in outs if "launchpad" in p.lower()), None)
            if not in_name:
                self.status = "Launchpad not found"
                return
            self.inport = mido.open_input(in_name)
            if out_name:
                self.outport = mido.open_output(out_name)
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
        self.geometry("1080x720")

        self.config_model: Config = load_config(CONFIG_PATH)
        self.midi = MidiBridge()
        self.entities: list[str] = []
        self.learn_target = None  # tk.Entry awaiting a captured number
        self.current_room: Room | None = None
        self.current_action: Action | None = None

        self._build_ui()
        self._load_entities_async()
        self._refresh_rooms()
        self._poll_midi()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- layout --------------------------------------------------------

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        self.status_var = tk.StringVar(value=self.midi.status)
        ttk.Label(top, textvariable=self.status_var).pack(side="left")
        ttk.Button(top, text="Reconnect MIDI", command=self._reconnect).pack(
            side="right"
        )
        ttk.Button(top, text="Save config.json", command=self._save).pack(
            side="right", padx=6
        )
        ttk.Button(top, text="Reload", command=self._reload).pack(side="right")

        body = ttk.Frame(self, padding=6)
        body.pack(fill="both", expand=True)

        # --- left: rooms ---
        left = ttk.LabelFrame(body, text="Rooms", padding=6)
        left.pack(side="left", fill="y")
        self.rooms_list = tk.Listbox(left, width=22, exportselection=False)
        self.rooms_list.pack(fill="y", expand=True)
        self.rooms_list.bind("<<ListboxSelect>>", lambda e: self._on_room_select())
        rb = ttk.Frame(left)
        rb.pack(fill="x", pady=4)
        ttk.Button(rb, text="Add", width=6, command=self._add_room).pack(side="left")
        ttk.Button(rb, text="Rename", width=7, command=self._rename_room).pack(
            side="left"
        )
        ttk.Button(rb, text="Del", width=5, command=self._del_room).pack(side="left")
        rk = ttk.Frame(left)
        rk.pack(fill="x")
        ttk.Label(rk, text="Selector CC:").pack(side="left")
        self.room_key_var = tk.StringVar()
        e = ttk.Entry(rk, textvariable=self.room_key_var, width=6)
        e.pack(side="left")
        ttk.Button(rk, text="Learn", width=6, command=lambda: self._learn(e)).pack(
            side="left"
        )
        self.room_key_var.trace_add("write", lambda *a: self._on_room_key_edit())

        # --- middle: grid ---
        mid = ttk.LabelFrame(body, text="Grid (click a pad)", padding=6)
        mid.pack(side="left", fill="both", expand=True, padx=6)
        self.grid_frame = ttk.Frame(mid)
        self.grid_frame.pack()
        self.cell_buttons: dict[tuple[int, int], tk.Button] = {}
        for r in range(GRID):
            for c in range(GRID):
                b = tk.Button(
                    self.grid_frame,
                    width=4,
                    height=2,
                    command=lambda r=r, c=c: self._on_cell(r, c),
                )
                b.grid(row=r, column=c, padx=1, pady=1)
                self.cell_buttons[(r, c)] = b
        self._default_bg = self.cell_buttons[(0, 0)].cget("bg")
        self._default_fg = self.cell_buttons[(0, 0)].cget("fg")
        ttk.Label(mid, text="Unplaced actions:").pack(anchor="w", pady=(8, 0))
        self.unplaced = tk.Listbox(mid, height=4)
        self.unplaced.pack(fill="x")
        self.unplaced.bind("<<ListboxSelect>>", lambda e: self._on_unplaced())

        # --- right: action editor ---
        right = ttk.LabelFrame(body, text="Macro", padding=6)
        right.pack(side="left", fill="y")
        self._build_editor(right)

    def _build_editor(self, parent) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Pad (note):").pack(side="left")
        self.key_var = tk.StringVar()
        ke = ttk.Entry(row, textvariable=self.key_var, width=6)
        ke.pack(side="left")
        ttk.Button(row, text="Learn", width=6, command=lambda: self._learn(ke)).pack(
            side="left"
        )

        trow = ttk.Frame(parent)
        trow.pack(fill="x", pady=2)
        ttk.Label(trow, text="Type:").pack(side="left")
        self.type_var = tk.StringVar(value="entity")
        ttk.Combobox(
            trow,
            textvariable=self.type_var,
            values=["entity", "preset"],
            width=10,
            state="readonly",
        ).pack(side="left")
        self.type_var.trace_add("write", lambda *a: self._sync_type_fields())

        # entity fields
        self.entity_frame = ttk.Frame(parent)
        ttk.Label(self.entity_frame, text="Entities:").pack(anchor="w")
        self.entities_list = tk.Listbox(self.entity_frame, height=6, width=34)
        self.entities_list.pack(fill="x")
        erow = ttk.Frame(self.entity_frame)
        erow.pack(fill="x", pady=2)
        self.entity_pick = ttk.Combobox(erow, width=26)
        self.entity_pick.pack(side="left")
        ttk.Button(erow, text="+", width=3, command=self._add_entity).pack(side="left")
        ttk.Button(erow, text="-", width=3, command=self._remove_entity).pack(
            side="left"
        )

        # preset field
        self.preset_frame = ttk.Frame(parent)
        ttk.Label(self.preset_frame, text="Preset:").pack(side="left")
        self.preset_var = tk.StringVar()
        self.preset_pick = ttk.Combobox(
            self.preset_frame,
            textvariable=self.preset_var,
            values=self._scan_presets(),
            width=18,
            state="readonly",
        )
        self.preset_pick.pack(side="left")

        # colors
        crow = ttk.Frame(parent)
        crow.pack(fill="x", pady=6)
        self.on_color_var = tk.IntVar(value=21)
        self.off_color_var = tk.IntVar(value=5)
        self._color_widget(crow, "On", self.on_color_var)
        self._color_widget(crow, "Off", self.off_color_var)

        brow = ttk.Frame(parent)
        brow.pack(fill="x", pady=8)
        ttk.Button(brow, text="Apply", command=self._apply_action).pack(side="left")
        ttk.Button(brow, text="Delete macro", command=self._delete_action).pack(
            side="left", padx=6
        )
        self._sync_type_fields()

    def _color_widget(self, parent, label, var) -> None:
        f = ttk.Frame(parent)
        f.pack(side="left", padx=6)
        ttk.Label(f, text=label).pack()
        sw = tk.Label(f, width=4, height=2, bg=hex_color(var.get()))
        sw.pack()
        sp = ttk.Spinbox(f, from_=0, to=127, textvariable=var, width=5)
        sp.pack()

        def on_change(*_):
            try:
                sw.configure(bg=hex_color(var.get()))
            except Exception:
                pass

        var.trace_add("write", on_change)
        ttk.Button(
            f, text="Test", width=5, command=lambda: self._test_color(var)
        ).pack()

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
            load_dotenv()
            ha = HAClient(os.getenv("HASS_URL"), os.getenv("HASS_TOKEN"))
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
            self.rooms_list.insert("end", f"{r.name}  (CC {r.room_key})")
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
        self.room_key_var.set(str(self.current_room.room_key))
        self._refresh_grid()
        self._clear_editor()

    def _on_room_key_edit(self) -> None:
        if not self.current_room:
            return
        try:
            self.current_room.room_key = int(self.room_key_var.get())
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
        for b in self.cell_buttons.values():
            b.configure(
                text="", bg=self._default_bg, fg=self._default_fg, relief="raised"
            )
        self.unplaced.delete(0, "end")
        self._unplaced_actions: list[Action] = []
        if not self.current_room:
            return

        # room selector buttons across all rooms (context)
        for room in self.config_model.rooms:
            cell = cell_for_number(room.room_key)
            if cell and cell in self.cell_buttons:
                b = self.cell_buttons[cell]
                b.configure(text="RM", bg="#444444", fg="white")

        for act in self.current_room.actions:
            cell = cell_for_number(act.key)
            label = act.preset[:4] if act.is_preset else str(act.key)
            if cell and cell in self.cell_buttons:
                self.cell_buttons[cell].configure(
                    text=label, bg=hex_color(act.on_color), fg="black"
                )
            else:
                self._unplaced_actions.append(act)
                self.unplaced.insert("end", f"{act.key}: {label}")

    def _on_cell(self, r: int, c: int) -> None:
        if not self.current_room:
            return
        # find the number this cell represents
        number = self._number_for_cell(r, c)
        act = next(
            (a for a in self.current_room.actions if cell_for_number(a.key) == (r, c)),
            None,
        )
        if act is None:
            if number is None:
                return
            if not messagebox.askyesno("New macro", f"Add a macro on pad {number}?"):
                return
            act = Action(key=number, on_color=21, off_color=5, entity_ids=[])
            self.current_room.actions.append(act)
            self._refresh_grid()
        self._edit_action(act)

    def _number_for_cell(self, r: int, c: int) -> int | None:
        for n in range(0, 100):
            if cell_for_number(n) == (r, c):
                return n
        return None

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
        self._refresh_grid()

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
                if self.learn_target is not None:
                    self.learn_target.delete(0, "end")
                    self.learn_target.insert(0, str(number))
                    self.learn_target = None
                    self.status_var.set(f"Captured {kind} {number}")
        except queue.Empty:
            pass
        self.after(50, self._poll_midi)

    def _reconnect(self) -> None:
        self.midi.connect()
        self.status_var.set(self.midi.status)

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
        messagebox.showinfo(
            "Saved",
            "config.json written.\nRestart the daemon to apply:\n"
            "sudo systemctl restart launchpad_controller",
        )

    def _reload(self) -> None:
        self.config_model = load_config(CONFIG_PATH)
        self._refresh_rooms()

    def _on_close(self) -> None:
        self.midi.close()
        self.destroy()


def main() -> None:
    ManageApp().mainloop()


if __name__ == "__main__":
    main()
