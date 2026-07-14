// Left panel: rooms as selector rows, each showing a live count of how many
// of its macros currently have an entity on (mirrors the daemon's room-select
// "any entity on" LED logic).
export default function RoomList({ model, ha, activeId, onSelect }) {
  const onCount = (room) =>
    room.actions.filter((a) => a.entityIds.some((e) => ha.isOn(e))).length;

  return (
    <div className="panel rooms">
      <div className="eyebrow">Rooms / Scenes</div>

      <div className="room-list">
        {model.rooms.map((room) => {
          const count = onCount(room);
          const active = room.id === activeId;
          return (
            <button
              key={room.id}
              className={`room-row${active ? " active" : ""}`}
              onClick={() => onSelect(room.id)}
            >
              <span className="room-accent" />
              <span className="room-name">{room.name}</span>
              {count > 0 && (
                <span className="room-count">
                  <span className="dot" />
                  {count}
                </span>
              )}
              <span className="cc-badge">CC {room.roomKey}</span>
            </button>
          );
        })}
      </div>

      <div className="grow" />

      <div className="crud">
        <button className="btn" disabled title="Editing rooms is read-only in the web dashboard">
          Add
        </button>
        <button className="btn ghost" disabled>
          Rename
        </button>
        <button className="btn ghost" disabled>
          Delete
        </button>
      </div>

      <div className="eyebrow">Selector button (CC)</div>
      <div className="sel-row">
        <div className="field">
          <input value={model.rooms.find((r) => r.id === activeId)?.roomKey ?? ""} readOnly />
        </div>
        <button className="btn ghost" disabled title="Learn needs a connected Launchpad">
          Learn
        </button>
      </div>
    </div>
  );
}
