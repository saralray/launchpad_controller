import time
import threading

# timing (seconds)
WAVE_DELAY = 0.15
HOLD_TIME = 0.3

_running = False
_thread = None


def _wave_loop(ha):
    lights = ha.all_lights()

    if not lights:
        return

    while _running:
        # ---- WAVE ON ----
        for entity_id in lights:
            if not _running:
                return
            ha.turn_on(entity_id)
            time.sleep(WAVE_DELAY)

        time.sleep(HOLD_TIME)

        # ---- WAVE OFF ----
        for entity_id in lights:
            if not _running:
                return
            ha.turn_off(entity_id)
            time.sleep(WAVE_DELAY)

        time.sleep(HOLD_TIME)


def stop():
    global _running
    _running = False
    time.sleep(0.2)
    print("🛑 Wave stopped")


def run(ha):
    global _running, _thread

    # toggle behavior
    if _running:
        stop()
        return

    print("🌊 Wave started")
    _running = True

    _thread = threading.Thread(
        target=_wave_loop,
        args=(ha,),
        daemon=True
    )
    _thread.start()
