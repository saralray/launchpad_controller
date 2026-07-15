"""Launchpad MIDI surface: port discovery with hot-plug resilience and
LED output. Never lets exceptions escape into the main loop.
"""

from __future__ import annotations

import time

import mido

from . import device


class MidiSurface:
    def __init__(self):
        self.inport = None
        self.outport = None
        self.in_name: str | None = None
        self.out_name: str | None = None
        # layout SysEx to send whenever the device (re)connects; None = leave
        # the surface in whatever layout it powers up in (historical default).
        self.startup_layout: int | None = None

    def open(self) -> None:
        """Block until both Launchpad in/out ports appear, then open them."""
        while True:
            ins = mido.get_input_names()
            outs = mido.get_output_names()

            in_name = device.pick_launchpad_port(ins)
            out_name = device.pick_launchpad_port(outs)

            if in_name and out_name:
                self.inport = mido.open_input(in_name)
                self.outport = mido.open_output(out_name)
                self.in_name = in_name
                self.out_name = out_name
                if self.startup_layout is not None:
                    self.select_layout(self.startup_layout)
                print(f"✅ Connected: {in_name}")
                return

            time.sleep(1)

    def still_present(self) -> bool:
        try:
            return (
                self.in_name in mido.get_input_names()
                and self.out_name in mido.get_output_names()
            )
        except Exception:
            return False

    def iter_pending(self):
        return self.inport.iter_pending() if self.inport else iter(())

    def set_programmer_mode(self, on: bool = True) -> None:
        """Select the Launchpad's Programmer ('User') layout. Best-effort."""
        if not self.outport:
            return
        try:
            self.outport.send(mido.Message("sysex", data=device.layout_sysex(on)))
        except Exception:
            pass

    def select_layout(self, layout: int) -> None:
        """Select a surface layout (device.CUSTOM_1 etc). Best-effort."""
        if not self.outport:
            return
        try:
            self.outport.send(
                mido.Message("sysex", data=device.select_layout_sysex(layout))
            )
        except Exception:
            pass

    def set_pad(self, key: int, val: int, is_cc: bool) -> None:
        if not self.outport:
            return
        self.outport.send(
            mido.Message("control_change", control=key, value=val)
            if is_cc
            else mido.Message("note_on", note=key, velocity=val)
        )

    def close(self) -> None:
        try:
            if self.inport:
                self.inport.close()
            if self.outport:
                self.outport.close()
        except Exception:
            pass
