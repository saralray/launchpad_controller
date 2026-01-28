import mido

# Auto-detect input port for Launchpad Mini MK3
input_port = next((p for p in mido.get_input_names() if "Launchpad Mini MK3" in p), None)

if not input_port:
    print("❌ Launchpad Mini Mk3 input port not found.")
    exit()

print(f"🎹 Listening on: {input_port}")
print("🔍 Press any key on Launchpad Mini Mk3 (Ctrl+C to exit)\n")

with mido.open_input(input_port) as inport:
    try:
        for msg in inport:
            if msg.type == "note_on" or msg.type == "note_off":
                status = "🔘 PRESSED" if msg.velocity > 0 else "⚪️ RELEASED"
                print(f"{status} → Note {msg.note}, Velocity {msg.velocity}")
            else:
                print(f"Other message: {msg}")
    except KeyboardInterrupt:
        print("\n🛑 Exiting.")
