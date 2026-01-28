import time
import random
import threading

# Global control flag (module-level = persistent)
_running = False
_threads = []


def _light_chaos_worker(ha, entity_id):
    while _running:
        time.sleep(random.uniform(0.05, 0.6))
        mode = random.random()

        if mode < 0.5:
            ha.turn_on(entity_id)
            time.sleep(random.uniform(0.05, 0.2))
            ha.turn_off(entity_id)

        elif mode < 0.8:
            ha.turn_on(entity_id, flash="short")

        else:
            ha.turn_on(entity_id)
            time.sleep(random.uniform(0.2, 0.8))
            ha.turn_off(entity_id)


def stop(ha):
    global _running
    _running = False

    # give threads time to exit
    time.sleep(0.2)

    for light in ha.all_lights():
        ha.turn_off(light)

    print("🛑 Chaos stopped")


def run(ha):
    global _running, _threads

    # Toggle behavior
    if _running:
        stop(ha)
        return

    _running = True
    _threads = []

    lights = ha.all_lights()
    print(f"💣 CHAOS MODE STARTED ({len(lights)} lights)")

    for entity_id in lights:
        t = threading.Thread(
            target=_light_chaos_worker,
            args=(ha, entity_id),
            daemon=True
        )
        t.start()
        _threads.append(t)
