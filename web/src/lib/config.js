// Load the daemon's real config.json (repo root) as the single source of truth
// for rooms and macros. Vite resolves this JSON import at build time; see
// vite.config.js `server.fs.allow` for the dev server.
import raw from "../../../config.json";

let uid = 0;
const nextId = () => `a${uid++}`;

// Normalize each action into a consistent shape the UI can rely on.
function normalizeAction(a) {
  const isPreset = a.preset != null;
  return {
    id: nextId(),
    key: a.key,
    isPreset,
    preset: a.preset ?? null,
    entityIds: isPreset ? [] : a.entity_ids ?? [],
    onColor: a.on_color ?? 21,
    offColor: a.off_color ?? 0,
    serviceData: a.service_data ?? null,
  };
}

// Parse ANY daemon-shaped config object into the UI model. Used for the bundled
// default, a config fetched at runtime, and configs the user imports — so the
// dashboard adapts to whatever rooms / entities a given Home Assistant setup has.
export function parseConfig(rawObj) {
  return {
    rooms: (rawObj?.rooms ?? []).map((r) => ({
      id: nextId(),
      name: r.name,
      roomKey: r.room_key,
      keyColorOn: r.room_key_color_on ?? 21,
      keyColorAnyOn: r.room_key_color_any_on ?? 9,
      keyColorOff: r.room_key_color_off ?? 5,
      actions: (r.actions ?? []).map(normalizeAction),
    })),
  };
}

// Bundled default: the repo's config.json, imported at build time as a fallback.
export function loadConfig() {
  return parseConfig(raw);
}

// Runtime load: prefer a config.json served next to the app (so swapping the
// file needs no rebuild); fall back to the bundled default. Returns { model,
// source } so the UI can show where the config came from.
export async function fetchConfig() {
  try {
    const res = await fetch("./config.json", { cache: "no-store" });
    if (res.ok) {
      const json = await res.json();
      if (json?.rooms) return { model: parseConfig(json), source: "served" };
    }
  } catch {
    /* not served in dev — fall back to the bundled copy */
  }
  return { model: loadConfig(), source: "bundled" };
}

// Validate + parse an imported config file's text.
export function parseConfigText(text) {
  const json = JSON.parse(text);
  if (!json || !Array.isArray(json.rooms)) {
    throw new Error('Not a valid config.json (missing "rooms" array).');
  }
  return parseConfig(json);
}

// Serialize back to the daemon's config.json shape (for Download JSON).
export function serializeConfig(model) {
  return {
    rooms: model.rooms.map((r) => ({
      name: r.name,
      room_key: r.roomKey,
      room_key_color_on: r.keyColorOn,
      room_key_color_any_on: r.keyColorAnyOn,
      room_key_color_off: r.keyColorOff,
      actions: r.actions.map((a) =>
        a.isPreset
          ? { key: a.key, preset: a.preset, on_color: a.onColor, off_color: a.offColor }
          : {
              key: a.key,
              entity_ids: a.entityIds,
              ...(a.serviceData ? { service_data: a.serviceData } : {}),
              on_color: a.onColor,
              off_color: a.offColor,
            }
      ),
    })),
  };
}

// Friendly label for an action, derived from its entities / preset.
export function actionLabel(a) {
  if (a.isPreset) return a.preset;
  if (!a.entityIds.length) return `pad ${a.key}`;
  if (a.entityIds.length > 1) return groupName(a.entityIds);
  return prettyEntity(a.entityIds[0]);
}

export function prettyEntity(id) {
  const name = id.split(".").slice(1).join(".");
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function groupName(ids) {
  // "light.co_working_space_ceiling_light_1..3" -> "Ceiling Light ×3"
  const base = prettyEntity(ids[0]).replace(/\s*\d+$/, "").trim();
  return `${base} ×${ids.length}`;
}

// Domain (light / switch / climate / fan) of an action's entities.
export function actionDomain(a) {
  if (a.isPreset) return "preset";
  return a.entityIds[0]?.split(".")[0] ?? "light";
}
