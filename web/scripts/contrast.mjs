/**
 * Contrast check.
 *
 * "Data legibility is a hard requirement, not a style preference." So the
 * palette gets measured rather than eyeballed: WCAG 2.1 relative-luminance
 * contrast for every foreground the telemetry actually uses, against every
 * surface it actually sits on.
 *
 * Thresholds applied here:
 *   4.5:1  small text — the IBM Plex Mono telemetry is 10-12px, so this is the
 *          bar for anything carrying a number or a label a judge must read.
 *   3.0:1  large/bold text (>=18.66px bold or >=24px) and non-text graphics
 *          such as the quadrant dots and divider strokes.
 *
 * Panels are SOLID, which is what makes this check meaningful: if the data sat
 * on translucent glass over a moving aurora, no static number would be
 * trustworthy.
 *
 *   npm run contrast
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));

/* Token values are READ from index.css rather than restated here. A duplicated
 * palette would drift the moment someone edited the stylesheet, and this check
 * would keep passing against colours the app no longer uses. */
const CSS = readFileSync(resolve(HERE, "../src/index.css"), "utf8");

function token(name) {
  const m = CSS.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!m) {
    console.error(`could not read ${name} from src/index.css`);
    process.exit(1);
  }
  return m[1];
}

/** The tooltip background is a one-off literal in InfoTip.jsx. */
function literalFrom(file, re, label) {
  const src = readFileSync(resolve(HERE, file), "utf8");
  const m = src.match(re);
  if (!m) {
    console.error(`could not read ${label} from ${file}`);
    process.exit(1);
  }
  return m[1];
}

const SURFACES = {
  "--bg-glass (panel)": token("--bg-glass"),
  "--color-surface (row)": token("--color-surface"),
  "--color-bg (page)": token("--color-bg"),
  "tooltip bg": literalFrom(
    "../src/components/InfoTip.jsx",
    /bg-\[(#[0-9a-fA-F]{6})\]/,
    "tooltip background"
  ),
};

const INK = {
  "--color-ink": token("--color-ink"),
  "--color-muted": token("--color-muted"),
  "--color-faint": token("--color-faint"),
};

const ACCENTS = {
  "--color-cyan": token("--color-cyan"),
  "--color-violet": token("--color-violet"),
  "--color-amber": token("--color-amber"),
  "--color-red": token("--color-red"),
};

/** Where each foreground is used, and therefore which bar it has to clear. */
const ROLES = [
  // Small text: numbers and labels.
  { fg: "--color-ink", min: 4.5, note: "tool names, observations, stat values" },
  { fg: "--color-muted", min: 4.5, note: "observations, verdicts, legend" },
  // faint is used for de-emphasised labels and captions, still read at 10px.
  { fg: "--color-faint", min: 4.5, note: "turn indices, captions, axis labels" },
  // Accents carry numbers (novelty readings, fire turns) so they take the
  // small-text bar too, not the graphics bar.
  { fg: "--color-cyan", min: 4.5, note: "novelty readings, PRODUCTIVE, pass states" },
  { fg: "--color-violet", min: 4.5, note: "BATCH quadrant label and dots" },
  { fg: "--color-amber", min: 4.5, note: "THRASH, WATCHING, false-trip lane" },
  { fg: "--color-red", min: 4.5, note: "sub-floor novelty, STUCK, halt rule" },
];

function srgbToLinear(c) {
  const v = c / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return (
    0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
  );
}

function contrast(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

const ALL_FG = { ...INK, ...ACCENTS };
const problems = [];
const rows = [];

for (const role of ROLES) {
  const fgHex = ALL_FG[role.fg];
  for (const [surfaceName, surfaceHex] of Object.entries(SURFACES)) {
    const ratio = contrast(fgHex, surfaceHex);
    const pass = ratio >= role.min;
    rows.push({
      fg: role.fg,
      surface: surfaceName,
      ratio,
      min: role.min,
      pass,
      note: role.note,
    });
    if (!pass) {
      problems.push(
        `${role.fg} (${fgHex}) on ${surfaceName} (${surfaceHex}): ` +
          `${ratio.toFixed(2)}:1, needs ${role.min}:1 — used for ${role.note}`
      );
    }
  }
}

// Report the full matrix so a regression is visible, not just failures.
const width = Math.max(...rows.map((r) => r.fg.length));
let lastFg = null;
console.log("");
for (const r of rows) {
  if (r.fg !== lastFg) {
    console.log(`${r.fg.padEnd(width)}  (${r.note})`);
    lastFg = r.fg;
  }
  console.log(
    `${" ".repeat(width)}  ${r.pass ? "ok  " : "FAIL"} ` +
      `${r.ratio.toFixed(2).padStart(5)}:1  vs ${r.surface}`
  );
}

if (problems.length) {
  console.error(`\ncontrast CHECK FAILED — ${problems.length} pair(s) below threshold:\n`);
  for (const p of problems) console.error(`  · ${p}`);
  console.error("");
  process.exit(1);
}

console.log(
  `\ncontrast check OK` +
    `\n  ${rows.length} foreground/surface pairs, all at or above their threshold` +
    `\n  panels are solid, so these ratios hold regardless of the aurora\n`
);
