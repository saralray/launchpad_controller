// Port of launchpad/palette.py — approximate RGB for Launchpad Mini MK3
// velocity color indices (0-127). Exact color always comes from the device;
// this is the coarse ramp used for on-screen swatches, matching the daemon's
// GUI so the web dashboard shows the same colors.

const KNOWN = {
  0: [20, 20, 20], // off
  1: [60, 60, 60], // dim grey
  5: [200, 200, 200], // white
  9: [255, 170, 0], // amber
  13: [255, 255, 0], // yellow
  21: [0, 220, 0], // green
  33: [0, 180, 255], // cyan/blue
  54: [150, 0, 255], // violet
};

function hsvToRgb(h, s, v) {
  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  let r, g, b;
  switch (i % 6) {
    case 0: [r, g, b] = [v, t, p]; break;
    case 1: [r, g, b] = [q, v, p]; break;
    case 2: [r, g, b] = [p, v, t]; break;
    case 3: [r, g, b] = [p, q, v]; break;
    case 4: [r, g, b] = [t, p, v]; break;
    default: [r, g, b] = [v, p, q]; break;
  }
  return [r, g, b];
}

export function rgb(velocity) {
  let v = Math.max(0, Math.min(127, Math.trunc(velocity)));
  if (KNOWN[v]) return KNOWN[v];
  if (v === 0) return [20, 20, 20];
  const hue = ((v * 0.021) % 1 + 1) % 1;
  const [r, g, b] = hsvToRgb(hue, 0.85, 1.0);
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

export function hex(velocity) {
  const [r, g, b] = rgb(velocity);
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

export function mix(fg, bg, t) {
  return fg.map((f, i) => Math.round(f + (bg[i] - f) * t));
}

export function toHex([r, g, b]) {
  return `#${[r, g, b].map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`;
}

// Relative luminance (0-255 scale) — decides readable label color on a swatch.
export function lum([r, g, b]) {
  return 0.299 * r + 0.587 * g + 0.114 * b;
}
