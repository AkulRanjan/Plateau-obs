/**
 * Animation ownership check.
 *
 * The rule: one animation owner per element. Framer Motion owns the data views;
 * Anime.js owns only the trip timeline. Both libraries writing one node's
 * transform is a bug, and it is the kind of bug that shows up as jitter on a
 * projector rather than as an error in a console.
 *
 * This is a static check over the source, because the failure it guards is
 * introduced by editing a component, not by running it:
 *
 *   1. Every node Anime.js targets must NOT be a <motion.*> element.
 *   2. Anime.js must only be imported by its one designated hook.
 *   3. The selectors that hook uses must match the attributes actually in the
 *      markup — a renamed attribute would silently no-op.
 *
 *   npm run ownership
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "../src");

/** The only module allowed to import animejs. */
const ANIME_OWNER = "hooks/useTripSequence.js";

/** Attributes the Anime.js timeline targets. */
const ANIME_ATTRS = ["tripmarker", "pill", "flash"];

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.(jsx?|mjs)$/.test(full)) out.push(full);
  }
  return out;
}

const files = walk(SRC);
const problems = [];
const check = (ok, msg) => {
  if (!ok) problems.push(msg);
};

let animeImporters = [];
const foundAttrs = new Set();
let taggedNodes = 0;

for (const file of files) {
  const rel = relative(SRC, file);
  const src = readFileSync(file, "utf8");

  // --- 2. who imports animejs ---
  if (/from\s+["']animejs["']/.test(src)) animeImporters.push(rel);

  // --- 1. is any anime-targeted node also a motion element? ---
  // Match an opening tag and capture its name, for tags carrying an anime attr.
  const tagRe = /<([A-Za-z][\w.]*)((?:[^>"']|"[^"]*"|'[^']*')*?)>/g;
  let m;
  while ((m = tagRe.exec(src)) !== null) {
    const [, tagName, attrs] = m;
    const hit = ANIME_ATTRS.find((a) => attrs.includes(`data-plateau-${a}`));
    if (!hit) continue;

    taggedNodes += 1;
    foundAttrs.add(hit);

    check(
      !tagName.startsWith("motion."),
      `${rel}: <${tagName}> carries data-plateau-${hit}, which the Anime.js ` +
        `timeline animates. Framer Motion must not also own this node — ` +
        `move the attribute to a plain element, or retarget the timeline.`
    );
  }
}

check(
  animeImporters.length === 1 && animeImporters[0] === ANIME_OWNER,
  `animejs must be imported by ${ANIME_OWNER} alone, but is imported by: ` +
    `${animeImporters.join(", ") || "(nothing)"}`
);

// --- 3. do the hook's selectors match the markup? ---
const hookSrc = readFileSync(resolve(SRC, ANIME_OWNER), "utf8");
for (const attr of ANIME_ATTRS) {
  const selector = `[data-plateau-${attr}]`;
  check(
    hookSrc.includes(selector),
    `${ANIME_OWNER} no longer queries ${selector}`
  );
  check(
    foundAttrs.has(attr),
    `no element in src/ carries data-plateau-${attr}, but ${ANIME_OWNER} ` +
      `queries for it — the timeline step would silently no-op`
  );
}

if (problems.length) {
  console.error(`\nownership CHECK FAILED — ${problems.length} problem(s):\n`);
  for (const p of problems) console.error(`  · ${p}`);
  console.error("");
  process.exit(1);
}

console.log(
  `\nownership check OK` +
    `\n  files scanned   : ${files.length}` +
    `\n  animejs importer: ${animeImporters[0]} (sole)` +
    `\n  anime targets   : ${taggedNodes} node(s), none owned by Framer Motion` +
    `\n  attrs matched   : ${[...foundAttrs].map((a) => `data-plateau-${a}`).join(", ")}\n`
);
