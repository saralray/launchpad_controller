import { GRID, cellForNumber, isRound } from "../lib/layout.js";
import { rgb, mix, toHex, lum } from "../lib/palette.js";
import { actionLabel } from "../lib/config.js";
import NovationLogo from "./NovationLogo.jsx";

// A lit pad glows its velocity color with a soft halo, exactly like the device.
function padStyle(velocity) {
  const base = rgb(velocity);
  const top = mix(base, [255, 255, 255], 0.18);
  return {
    background: `linear-gradient(160deg, ${toHex(top)}, ${toHex(base)})`,
    boxShadow: `0 0 12px ${toHex(base)}99, inset 0 1px 0 rgba(255,255,255,0.25)`,
    color: lum(base) > 140 ? "#0a1207" : "#f4fbef",
  };
}

export default function PadGrid({ room, model, ha, selectedActionId, onSelectAction, onToggle }) {
  if (!room) return <div className="panel grid-panel" />;

  // Build a lookup of what sits at each display cell.
  const cells = new Map(); // "r,c" -> { kind, action, velocity, label }

  // Room selectors from every room give spatial context (like the daemon's
  // top-row LEDs). The active room's own selector glows brighter.
  for (const r of model.rooms) {
    const cell = cellForNumber(r.roomKey, true);
    if (!cell) continue;
    const anyOn = r.actions.some((a) => a.entityIds.some((e) => ha.isOn(e)));
    const velocity = r === room ? r.keyColorAnyOn : anyOn ? r.keyColorAnyOn : r.keyColorOff;
    cells.set(`${cell.r},${cell.c}`, { kind: "selector", velocity, label: "RM" });
  }

  const unplaced = [];
  for (const a of room.actions) {
    const cell = cellForNumber(a.key, false);
    const on = a.isPreset ? true : a.entityIds.some((e) => ha.isOn(e));
    const velocity = a.isPreset ? a.onColor : on ? a.onColor : a.offColor;
    if (cell) {
      cells.set(`${cell.r},${cell.c}`, {
        kind: "macro",
        action: a,
        velocity,
        lit: on,
        label: a.isPreset ? a.preset.slice(0, 4).toUpperCase() : String(a.key),
      });
    } else {
      unplaced.push(a);
    }
  }

  const rows = [];
  for (let r = 0; r < GRID; r++) {
    const rowCells = [];
    for (let c = 0; c < GRID; c++) {
      const info = cells.get(`${r},${c}`);
      const round = isRound(r, c);
      const classes = ["pad"];
      if (round) classes.push("round");
      let style;
      let onClick;
      let title;
      if (info && info.kind === "macro") {
        classes.push("macro");
        if (info.lit) classes.push("lit");
        if (info.action.id === selectedActionId) classes.push("selected");
        style = padStyle(info.velocity);
        title = `${actionLabel(info.action)} · pad ${info.action.key}`;
        onClick = () => {
          onSelectAction(info.action.id);
          if (!info.action.isPreset) onToggle(info.action);
        };
      } else if (info && info.kind === "selector") {
        classes.push("lit");
        style = padStyle(info.velocity);
        title = "room selector";
      } else {
        classes.push("empty");
      }
      rowCells.push(
        <button key={c} className={classes.join(" ")} style={style} onClick={onClick} title={title}>
          {info && <span className="pad-label">{info.label}</span>}
        </button>
      );
    }
    rows.push(
      <div key={r} className="deck-row">
        {rowCells}
      </div>
    );
  }

  return (
    <div className="panel grid-panel">
      <div className="grid-head">
        <span className="eyebrow">Pad grid</span>
        <span className="room-title">{room.name}</span>
        <div className="grow" />
        <button className="btn ghost" disabled title="Map layout needs a connected Launchpad">
          Map layout
        </button>
        <NovationLogo height={16} />
      </div>

      <div className="deck">
        <div className="deck-rows">{rows}</div>
      </div>

      <div className="grid-help">
        Click a lit pad to toggle its entities · the selected macro opens in the editor · colors
        track live Home&nbsp;Assistant state
      </div>

      {unplaced.length > 0 && (
        <div className="unplaced">
          <div className="eyebrow">Unplaced macros</div>
          <div className="chips">
            {unplaced.map((a) => (
              <button key={a.id} className="chip" onClick={() => onSelectAction(a.id)}>
                <span className="chip-num">{a.key}</span>
                {actionLabel(a)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
