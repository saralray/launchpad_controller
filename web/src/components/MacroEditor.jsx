import { useState } from "react";
import { rgb, mix, toHex } from "../lib/palette.js";
import { actionLabel, actionDomain } from "../lib/config.js";

function ColorPicker({ value, onChange, onClose }) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" style={{ width: 420 }} onClick={(e) => e.stopPropagation()}>
        <h2>Pick pad color</h2>
        <div className="hint">Launchpad Mini MK3 palette — velocity index sent to the pad.</div>
        <div className="swatch-grid">
          {Array.from({ length: 128 }, (_, i) => (
            <button
              key={i}
              className={`swatch-cell${i === value ? " chosen" : ""}`}
              style={{ background: toHex(rgb(i)) }}
              title={`velocity ${i}`}
              onClick={() => {
                onChange(i);
                onClose();
              }}
            />
          ))}
        </div>
        <div className="dialog-actions">
          <button className="btn primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

function Swatch({ label, velocity, onPick }) {
  const base = rgb(velocity);
  const top = mix(base, [255, 255, 255], 0.2);
  return (
    <button className="swatch-card" onClick={onPick}>
      <span
        className="swatch"
        style={{
          background: `linear-gradient(160deg, ${toHex(top)}, ${toHex(base)})`,
          boxShadow: `0 0 9px ${toHex(base)}80`,
        }}
      />
      <span className="swatch-meta">
        <span className="s-label">{label}</span>
        <span className="s-val">vel {velocity}</span>
      </span>
    </button>
  );
}

export default function MacroEditor({ room, action, ha, onPatch, onDelete, onToggle }) {
  const [picking, setPicking] = useState(null); // "on" | "off" | null

  if (!action) {
    return (
      <div className="panel editor">
        <div className="eyebrow">Macro</div>
        <div className="placeholder-note">
          Select a pad on the grid to inspect its macro — the entities it drives, their live state,
          and its on/off colors.
        </div>
      </div>
    );
  }

  const on = action.isPreset ? true : action.entityIds.some((e) => ha.isOn(e));

  const addEntity = () => {
    const id = window.prompt("Entity id (e.g. light.kitchen):");
    if (id && id.trim()) onPatch({ entityIds: [...action.entityIds, id.trim()] });
  };
  const removeEntity = (id) => onPatch({ entityIds: action.entityIds.filter((e) => e !== id) });

  return (
    <div className="panel editor">
      <div className="editor-head">
        <span className="eyebrow">Macro</span>
        <div className="grow" />
        <span className="macro-name">{actionLabel(action)}</span>
      </div>

      <div className="eyebrow">Pad (note)</div>
      <div className="sel-row">
        <div className="field">
          <input
            value={action.key}
            onChange={(e) => {
              const n = parseInt(e.target.value, 10);
              if (!Number.isNaN(n)) onPatch({ key: n });
            }}
          />
        </div>
        <button className="btn ghost" disabled title="Learn needs a connected Launchpad">
          Learn
        </button>
      </div>

      <div className="eyebrow">Type</div>
      <div className="seg">
        <button className={action.isPreset ? "" : "active"} disabled>
          Entity
        </button>
        <button className={action.isPreset ? "active" : ""} disabled>
          Preset
        </button>
      </div>

      {action.isPreset ? (
        <>
          <div className="eyebrow">Preset</div>
          <div className="field">{action.preset}</div>
        </>
      ) : (
        <>
          <div className="eyebrow">
            Entities · {actionDomain(action)}
          </div>
          <div className="ent-list">
            {action.entityIds.length === 0 && <div className="ent-empty">No entities.</div>}
            {action.entityIds.map((e) => (
              <div className="ent-row" key={e}>
                <span className={`state-dot${ha.isOn(e) ? " on" : ""}`} />
                <span className="ent-name" title={e}>
                  {e}
                </span>
                <button className="ent-del" onClick={() => removeEntity(e)} title="Remove">
                  −
                </button>
              </div>
            ))}
          </div>
          <div className="pick-row">
            <button className="icon-btn" onClick={addEntity} title="Add entity">
              +
            </button>
            <span className="grid-help" style={{ textAlign: "left", margin: 0 }}>
              add a Home&nbsp;Assistant entity to this macro
            </span>
          </div>
        </>
      )}

      <div className="eyebrow">Colors</div>
      <div className="color-row">
        <Swatch label="ON" velocity={action.onColor} onPick={() => setPicking("on")} />
        <Swatch label="OFF" velocity={action.offColor} onPick={() => setPicking("off")} />
      </div>

      {!action.isPreset && (
        <button className={`toggle-big${on ? " on" : ""}`} onClick={onToggle}>
          {on ? "Turn off" : "Turn on"}
        </button>
      )}

      <div className="editor-actions">
        <button className="btn grow" disabled title="Edits apply in-memory; use Download JSON to persist">
          Apply changes
        </button>
        <button className="btn danger" onClick={onDelete}>
          Delete
        </button>
      </div>

      {picking && (
        <ColorPicker
          value={picking === "on" ? action.onColor : action.offColor}
          onChange={(v) => onPatch(picking === "on" ? { onColor: v } : { offColor: v })}
          onClose={() => setPicking(null)}
        />
      )}
    </div>
  );
}
