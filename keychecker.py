import mido

from launchpad import device

# Listen on the same port the daemon uses, in the device's own layout — no
# forced mode. The numbers printed here are the real ones config.json /
# the calibration wizard should use.
in_name = device.pick_launchpad_port(mido.get_input_names())

if not in_name:
    print("❌ Launchpad Mini Mk3 input port not found.")
    print("   Ports seen:", mido.get_input_names())
    exit()

print(f"🎹 Listening on: {in_name}")
print("🔍 Press any key on Launchpad Mini Mk3 (Ctrl+C to exit)\n")

with mido.open_input(in_name) as inport:
    try:
        for msg in inport:
            if msg.type == "note_on" or msg.type == "note_off":
                status = "🔘 PRESSED" if msg.velocity > 0 else "⚪️ RELEASED"
                print(f"{status} → Note {msg.note}, Velocity {msg.velocity}")
            else:
                print(f"Other message: {msg}")
    except KeyboardInterrupt:
        print("\n🛑 Exiting.")
