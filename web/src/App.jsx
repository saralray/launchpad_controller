import { useEffect, useMemo, useRef, useState } from "react";
import { loadConfig, fetchConfig, parseConfigText, serializeConfig } from "./lib/config.js";
import { HAClient, loadConnection } from "./lib/haClient.js";
import TopBar from "./components/TopBar.jsx";
import RoomList from "./components/RoomList.jsx";
import PadGrid from "./components/PadGrid.jsx";
import MacroEditor from "./components/MacroEditor.jsx";
import ConnectionDialog from "./components/ConnectionDialog.jsx";

export default function App() {
  const [model, setModel] = useState(() => loadConfig());
  const [roomId, setRoomId] = useState(() => model.rooms[0]?.id ?? null);
  const [actionId, setActionId] = useState(null);
  const [connOpen, setConnOpen] = useState(false);
  const [toast, setToast] = useState(null);
  const [, forceTick] = useState(0);

  // One long-lived HA client; re-render whenever its state cache changes.
  const haRef = useRef(null);
  if (!haRef.current) {
    haRef.current = new HAClient();
    haRef.current.seedDemo(model);
  }
  const ha = haRef.current;

  useEffect(() => {
    const unsub = ha.subscribe(() => forceTick((n) => n + 1));
    const conn = loadConnection();
    if (conn.url && conn.token) ha.connect(conn.url, conn.token);
    // Prefer a config.json served next to the app, so swapping it needs no
    // rebuild. Falls back to the bundled default (already in state).
    let cancelled = false;
    fetchConfig().then(({ model: m, source }) => {
      if (cancelled || source !== "served") return;
      setModel(m);
      setRoomId(m.rooms[0]?.id ?? null);
      setActionId(null);
      ha.seedDemo(m);
    });
    return () => {
      cancelled = true;
      unsub();
    };
  }, [ha]);

  const room = useMemo(
    () => model.rooms.find((r) => r.id === roomId) ?? model.rooms[0],
    [model, roomId]
  );
  const action = useMemo(
    () => room?.actions.find((a) => a.id === actionId) ?? null,
    [room, actionId]
  );

  const showToast = (msg) => {
    setToast(msg);
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => setToast(null), 2600);
  };

  // ---- mutations (in-memory; export via Download JSON) -----------------
  const updateModel = (fn) =>
    setModel((m) => {
      const next = structuredClone(m);
      fn(next);
      return next;
    });

  const patchAction = (patch) =>
    updateModel((m) => {
      const r = m.rooms.find((x) => x.id === room.id);
      const a = r?.actions.find((x) => x.id === action.id);
      if (a) Object.assign(a, patch);
    });

  const deleteAction = () => {
    updateModel((m) => {
      const r = m.rooms.find((x) => x.id === room.id);
      if (r) r.actions = r.actions.filter((x) => x.id !== action.id);
    });
    setActionId(null);
  };

  const downloadJSON = () => {
    const blob = new Blob([JSON.stringify(serializeConfig(model), null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "config.json";
    a.click();
    URL.revokeObjectURL(url);
    showToast("config.json downloaded — drop it in the daemon folder to apply.");
  };

  const applyModel = (m, note) => {
    setModel(m);
    setRoomId(m.rooms[0]?.id ?? null);
    setActionId(null);
    if (ha.passive) ha.seedDemo(m);
    if (note) showToast(note);
  };

  const reload = async () => {
    const { model: m, source } = await fetchConfig();
    applyModel(m, source === "served" ? "Config reloaded from server." : "Reloaded bundled config.");
  };

  // Import an arbitrary daemon-shaped config.json so the dashboard can drive any
  // Home Assistant setup, not just the bundled one.
  const importConfig = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const m = parseConfigText(String(reader.result));
        applyModel(m, `Imported ${file.name} — ${m.rooms.length} rooms.`);
      } catch (e) {
        showToast(`Import failed: ${e.message}`);
      }
    };
    reader.readAsText(file);
  };

  return (
    <div className="app">
      <TopBar
        ha={ha}
        onConnection={() => setConnOpen(true)}
        onImport={importConfig}
        onReload={reload}
        onDownload={downloadJSON}
        onSave={() =>
          showToast(
            ha.passive
              ? "Web dashboard is control-only — use Download JSON to save config."
              : "Live control is applied directly; use Download JSON to persist macro edits."
          )
        }
      />

      <div className="body">
        <RoomList
          model={model}
          ha={ha}
          activeId={room?.id}
          onSelect={(id) => {
            setRoomId(id);
            setActionId(null);
          }}
        />
        <PadGrid
          room={room}
          model={model}
          ha={ha}
          selectedActionId={actionId}
          onSelectAction={setActionId}
          onToggle={(a) => ha.toggle(a.entityIds)}
        />
        <MacroEditor
          room={room}
          action={action}
          ha={ha}
          onPatch={patchAction}
          onDelete={deleteAction}
          onToggle={() => action && ha.toggle(action.entityIds)}
        />
      </div>

      {connOpen && (
        <ConnectionDialog
          ha={ha}
          onClose={() => setConnOpen(false)}
          onConnected={(msg) => showToast(msg)}
        />
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
