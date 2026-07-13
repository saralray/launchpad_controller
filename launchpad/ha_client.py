"""Home Assistant client: local state cache, non-blocking service calls,
REST state poll, and a persistent WebSocket state subscription.

PASSIVE_MODE: when URL/token are absent, every network call is a no-op and
the local `states` cache is driven only by optimistic writes from the
controller. The rest of the app treats a passive client transparently.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable

import requests
import urllib3
import websocket

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class HAClient:
    def __init__(self, url: str | None, token: str | None):
        self.url = url
        self.token = token
        self.passive = not (url and token)
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.states: dict[str, dict] = {}
        self._states_ts = 0.0

    # ---- state helpers -------------------------------------------------

    def state(self, entity_id: str) -> str | None:
        return self.states.get(entity_id, {}).get("state")

    def set_local(self, entity_id: str, state: str) -> None:
        """Optimistically update the cache so LEDs react instantly."""
        self.states[entity_id] = {"state": state}

    # ---- service calls (fire-and-forget) -------------------------------

    def call(self, domain: str, svc: str, data: dict) -> None:
        if self.passive:
            return
        threading.Thread(
            target=requests.post,
            kwargs=dict(
                url=f"{self.url}/api/services/{domain}/{svc}",
                headers=self.headers,
                json=data,
                timeout=3,
                verify=False,
            ),
            daemon=True,
        ).start()

    # ---- REST poll -----------------------------------------------------

    def refresh_states(self, force: bool = False) -> dict:
        if self.passive:
            return self.states
        if not force and time.time() - self._states_ts < 0.5:
            return self.states
        try:
            r = requests.get(
                f"{self.url}/api/states",
                headers=self.headers,
                timeout=3,
                verify=False,
            )
            r.raise_for_status()
            self.states = {s["entity_id"]: s for s in r.json()}
            self._states_ts = time.time()
        except Exception:
            pass
        return self.states

    # ---- WebSocket subscription ----------------------------------------

    def start_ws(self, on_state_change: Callable[[], None]) -> None:
        """Spawn a daemon thread holding a state_changed subscription.

        `on_state_change` is invoked after each applied update so the caller
        can repaint LEDs. Reconnects forever on drop.
        """
        if self.passive:
            return
        threading.Thread(
            target=self._ws_loop, args=(on_state_change,), daemon=True
        ).start()

    def _ws_loop(self, on_state_change: Callable[[], None]) -> None:
        ws_url = self.url.replace("http", "ws") + "/api/websocket"

        def on_open(ws):
            ws.send(json.dumps({"type": "auth", "access_token": self.token}))
            ws.send(
                json.dumps(
                    {
                        "id": 1,
                        "type": "subscribe_events",
                        "event_type": "state_changed",
                    }
                )
            )

        def on_message(ws, msg):
            try:
                d = json.loads(msg)
                e = d.get("event", {}).get("data", {})
                if "entity_id" in e and "new_state" in e:
                    self.states[e["entity_id"]] = e["new_state"]
                    self._states_ts = time.time()
                    on_state_change()
            except Exception:
                pass

        while True:
            try:
                websocket.WebSocketApp(
                    ws_url, on_open=on_open, on_message=on_message
                ).run_forever()
            except Exception:
                time.sleep(3)
