// Browser Home Assistant client — a faithful analogue of launchpad/ha_client.py.
//
//  * When a URL + long-lived token are configured, it polls /api/states over
//    REST, holds a persistent state_changed WebSocket subscription, and fires
//    service calls (turn_on / turn_off) — exactly like the daemon.
//  * With no credentials it runs in PASSIVE / demo mode: the state cache is
//    seeded locally and driven only by optimistic writes, so the dashboard is
//    fully explorable without a live Home Assistant. This mirrors the daemon's
//    PASSIVE_MODE contract.

// entity states that count as "lit" — matches app.ON_STATES.
export const ON_STATES = ["on", "cool"];

const LS_KEY = "launchpad.ha.connection";

export function loadConnection() {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || "{}");
  } catch {
    return {};
  }
}

export function saveConnection(conn) {
  localStorage.setItem(LS_KEY, JSON.stringify(conn));
}

export class HAClient {
  constructor() {
    this.url = null;
    this.token = null;
    this.passive = true;
    this.states = {}; // entity_id -> { state }
    this.status = "demo mode";
    this.listeners = new Set();
    this._ws = null;
    this._msgId = 1;
  }

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  _emit() {
    for (const fn of this.listeners) fn();
  }

  isOn(entityId) {
    return ON_STATES.includes(this.states[entityId]?.state);
  }

  setLocal(entityId, state) {
    this.states[entityId] = { state };
  }

  // Seed a plausible demo world so the dashboard looks alive offline. Fully
  // generic: works for ANY config's entities. A deterministic hash of each
  // entity id decides its state (so it's stable across re-renders), with
  // climate entities landing on "cool" when active — no hardcoded names.
  seedDemo(model) {
    const hash = (s) => {
      let h = 2166136261;
      for (let i = 0; i < s.length; i++) {
        h ^= s.charCodeAt(i);
        h = Math.imul(h, 16777619);
      }
      return h >>> 0;
    };
    this.states = {};
    for (const room of model.rooms) {
      for (const a of room.actions) {
        for (const e of a.entityIds) {
          const active = hash(e) % 5 < 2; // ~40% on, deterministic
          this.states[e] = { state: active ? (e.startsWith("climate.") ? "cool" : "on") : "off" };
        }
      }
    }
    this._emit();
  }

  // ---- connection -----------------------------------------------------

  async connect(url, token) {
    this.url = url?.replace(/\/+$/, "") || null;
    this.token = token || null;
    this.passive = !(this.url && this.token);
    if (this.passive) {
      this.status = "demo mode";
      this._closeWs();
      this._emit();
      return { ok: false, passive: true };
    }
    this.status = "connecting…";
    this._emit();
    const res = await this.refreshStates();
    if (res.ok) {
      this.status = `connected · ${res.count} entities`;
      this._startWs();
    } else {
      this.status = res.error || "connection failed";
    }
    this._emit();
    return res;
  }

  async refreshStates() {
    if (this.passive) return { ok: false, passive: true };
    try {
      const r = await fetch(`${this.url}/api/states`, {
        headers: { Authorization: `Bearer ${this.token}` },
      });
      if (!r.ok) return { ok: false, error: `HTTP ${r.status}` };
      const list = await r.json();
      for (const s of list) this.states[s.entity_id] = { state: s.state };
      this._emit();
      return { ok: true, count: list.length };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  }

  _startWs() {
    this._closeWs();
    const wsUrl = this.url.replace(/^http/, "ws") + "/api/websocket";
    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      return;
    }
    this._ws = ws;
    ws.onmessage = (ev) => {
      let d;
      try {
        d = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (d.type === "auth_required") {
        ws.send(JSON.stringify({ type: "auth", access_token: this.token }));
      } else if (d.type === "auth_ok") {
        ws.send(
          JSON.stringify({ id: this._msgId++, type: "subscribe_events", event_type: "state_changed" })
        );
      } else if (d.type === "event") {
        const e = d.event?.data;
        if (e?.entity_id && e.new_state) {
          this.states[e.entity_id] = { state: e.new_state.state };
          this._emit();
        }
      }
    };
    ws.onclose = () => {
      if (this._ws === ws && !this.passive) setTimeout(() => this._startWs(), 3000);
    };
    ws.onerror = () => ws.close();
  }

  _closeWs() {
    if (this._ws) {
      const ws = this._ws;
      this._ws = null;
      try {
        ws.close();
      } catch {
        /* ignore */
      }
    }
  }

  // ---- control (optimistic, fire-and-forget) --------------------------

  toggle(entityIds) {
    if (!entityIds?.length) return;
    const turningOn = !entityIds.some((e) => this.isOn(e));
    const state = turningOn ? "on" : "off";
    const svc = turningOn ? "turn_on" : "turn_off";
    for (const e of entityIds) {
      this.setLocal(e, e.startsWith("climate.") && turningOn ? "cool" : state);
      this.call(e.split(".")[0], svc, { entity_id: e });
    }
    this._emit();
  }

  call(domain, svc, data) {
    if (this.passive) return;
    fetch(`${this.url}/api/services/${domain}/${svc}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${this.token}`, "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).catch(() => {});
  }
}
