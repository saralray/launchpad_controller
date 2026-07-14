import { useRef } from "react";

export default function TopBar({ ha, onConnection, onImport, onReload, onDownload, onSave }) {
  const fileRef = useRef(null);
  const connected = !ha.passive && ha.status.startsWith("connected");
  const warn = !ha.passive && !connected;
  const ledClass = connected ? "led live" : warn ? "led warn" : "led";

  return (
    <div className="topbar">
      <div className="ident">
        <div className="ident-eyebrow">NOVATION LAUNCHPAD MINI MK3</div>
        <div className="ident-title">Macro Manager</div>
      </div>

      <div className="grow" />

      <div className="status-pill" title={ha.status}>
        <span className={ledClass} />
        <span>{ha.passive ? "demo mode · no Home Assistant" : ha.status}</span>
      </div>

      <div className="actions">
        <button className="btn ghost" onClick={onConnection}>
          Connection
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          style={{ display: "none" }}
          onChange={(e) => {
            onImport(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <button className="btn ghost" onClick={() => fileRef.current?.click()}>
          Import
        </button>
        <button className="btn ghost" onClick={onReload}>
          Reload
        </button>
        <button className="btn ghost" onClick={onDownload}>
          Download JSON
        </button>
        <button className="btn primary" onClick={onSave}>
          Save config
        </button>
      </div>
    </div>
  );
}
