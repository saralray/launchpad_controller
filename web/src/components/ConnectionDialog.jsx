import { useState } from "react";
import { loadConnection, saveConnection } from "../lib/haClient.js";

export default function ConnectionDialog({ ha, onClose, onConnected }) {
  const saved = loadConnection();
  const [url, setUrl] = useState(saved.url || "");
  const [token, setToken] = useState(saved.token || "");
  const [show, setShow] = useState(false);
  const [status, setStatus] = useState({ text: "", cls: "" });
  const [busy, setBusy] = useState(false);

  const test = async () => {
    if (!url.trim() || !token.trim()) {
      setStatus({ text: "Enter both a URL and a token.", cls: "warn" });
      return;
    }
    setBusy(true);
    setStatus({ text: "Testing…", cls: "" });
    const probe = Object.assign(Object.create(Object.getPrototypeOf(ha)), ha, {
      url: url.trim().replace(/\/+$/, ""),
      token: token.trim(),
      passive: false,
      states: {},
      listeners: new Set(),
    });
    const res = await probe.refreshStates();
    setBusy(false);
    if (res.ok) setStatus({ text: `Connected — ${res.count} entities found.`, cls: "ok" });
    else setStatus({ text: res.error || "Could not reach the server.", cls: "warn" });
  };

  const save = async () => {
    const conn = { url: url.trim(), token: token.trim() };
    saveConnection(conn);
    await ha.connect(conn.url, conn.token);
    onConnected(ha.passive ? "Switched to demo mode." : "Connected to Home Assistant.");
    onClose();
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>Home Assistant connection</h2>
        <div className="hint">
          Point the dashboard at your Home Assistant server to list entities and control them live.
          Leave blank to stay in demo mode. Stored in this browser only.
        </div>

        <label>
          <span className="eyebrow">Server URL</span>
          <div className="field">
            <input
              placeholder="https://homeassistant.local:8123"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
        </label>

        <label>
          <span className="eyebrow">Long-lived access token</span>
          <div className="field">
            <input
              type={show ? "text" : "password"}
              placeholder="eyJhbGciOi…"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </div>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} />
          Show token
        </label>

        <div className={`status-line ${status.cls}`}>{status.text}</div>

        <div className="dialog-actions">
          <button className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn" onClick={test} disabled={busy}>
            Test
          </button>
          <button className="btn primary" onClick={save} disabled={busy}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
