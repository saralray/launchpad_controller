// Grid geometry — the documented Novation Launchpad Mini MK3 X-Y layout,
// mirroring the geometry described in CLAUDE.md and used by the manage GUI:
//   - top CC row 91-99          -> display row 0 (round function buttons)
//   - right scene column x9      -> display col 8 (round buttons), tens = row
//   - main 8x8 notes 11-88       -> tens = row-from-bottom, ones = column
// Numbers off this grid (e.g. note 60 / 90) can't be placed and are returned
// as null, so the caller lists them as "unplaced".

export const GRID = 9;

export function cellForNumber(n, isCC = false) {
  n = Math.trunc(n);
  if (isCC) {
    if (n >= 91 && n <= 99) return { r: 0, c: n - 91 };
    return null;
  }
  const tens = Math.floor(n / 10);
  const ones = n % 10;
  if (tens >= 1 && tens <= 8 && ones >= 1 && ones <= 8) {
    return { r: 9 - tens, c: ones - 1 }; // main 8x8 -> display rows 1..8
  }
  if (tens >= 1 && tens <= 8 && ones === 9) {
    return { r: 9 - tens, c: 8 }; // right scene column
  }
  return null;
}

export function numberForCell(r, c) {
  if (r === 0) return { n: 91 + c, isCC: true }; // top CC row
  if (c === 8) return { n: (9 - r) * 10 + 9, isCC: false }; // scene column
  return { n: (9 - r) * 10 + (c + 1), isCC: false }; // main 8x8
}

// Is this display cell a round function/scene button (vs a square pad)?
export function isRound(r, c) {
  return r === 0 || c === 8;
}
