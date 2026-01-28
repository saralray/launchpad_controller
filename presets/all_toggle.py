# presets/all_toggle.py

def run(ha):
    lights = ha.all_lights()
    if not lights:
        return

    any_off = any(
        not ha.is_on(light)
        for light in lights
    )

    if any_off:
        print("💡 ALL ON")
        for light in lights:
            ha.turn_on(light)
    else:
        print("💤 ALL OFF")

        # stop effects safely
        for name in ("chaos", "wave"):
            try:
                __import__(f"presets.{name}").stop()
            except Exception:
                pass

        for light in lights:
            ha.turn_off(light)
