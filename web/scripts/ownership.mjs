/**
 * Animation ownership check.
 *
 * The rule: one animation owner per element. Framer Motion owns the data views;
 * Anime.js owns only the two timelines it is genuinely better at — the trip
 * sequence and the staggered lane reveal. Both libraries writing one node's
 * transform is a bug, and it is the kind of bug that shows up as jitter on a
 * projector rather than as an error in a console.
 *
 * This is a static check over the source, because the failure it guards is
 * introduced by editing a component, not by running it:
 *
 *   1. Every node Anime.js targets must NOT be a <motion.*> element.
 *   2. Anime.js may only be imported by its designated hooks, never by a
 *      component.
 *   3. The selectors those hooks use must match the attributes actually in the
 *      markup — a renamed attribute would silently no-op.
 *
 *   npm run ownership
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative, resolve, sep } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "../src");

/**
 * The only modules allowed to import animejs.
 *
 * Anime is confined to purpose-built hooks. It must never be imported by a
 * component, because that is how a component ends up with both libraries
 * writing the same node — the exact failure this check exists to prevent.
 */
const ANIME_OWNERS = ["hooks/useLaneReveal.js", "hooks/useTripSequence.js"];

/**
 * Attributes Anime.js targets, and which hook owns each.
 * Every one of these must sit on a plain element, never a <motion.*>.
 */
const ANIME_ATTRS = {
  tripmarker: "hooks/useTripSequence.js",
  pill: "hooks/useTripSequence.js",
  flash: "hooks/useTripSequence.js",
  lane: "hooks/useLaneReveal.js",
};

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
  // Normalised to forward slashes: `relative()` returns `hooks\useLaneReveal.js`
  // on Windows, which matches nothing in ANIME_OWNERS and made this check report
  // its two legitimate owners as violations of itself.
  const rel = relative(SRC, file).split(sep).join("/");
  const src = readFileSync(file, "utf8");

  // --- 2. who imports animejs ---
  if (/from\s+["']animejs["']/.test(src)) animeImporters.push(rel);

  // --- 1. is any anime-targeted node also a motion element? ---
  // Match an opening tag and capture its name, for tags carrying an anime attr.
  const tagRe = /<([A-Za-z][\w.]*)((?:[^>"']|"[^"]*"|'[^']*')*?)>/g;
  let m;
  while ((m = tagRe.exec(src)) !== null) {
    const [, tagName, attrs] = m;
    const hit = Object.keys(ANIME_ATTRS).find((a) =>
      attrs.includes(`data-plateau-${a}`)
    );
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

animeImporters = animeImporters.sort();
const unexpected = animeImporters.filter((f) => !ANIME_OWNERS.includes(f));
check(
  unexpected.length === 0,
  `animejs may only be imported by ${ANIME_OWNERS.join(" and ")}, but is also ` +
    `imported by: ${unexpected.join(", ")}. Anime belongs in a purpose-built ` +
    `hook, never in a component — that is how a node ends up with two owners.`
);

// --- 3. do each hook's selectors match the markup? ---
for (const [attr, owner] of Object.entries(ANIME_ATTRS)) {
  const selector = `[data-plateau-${attr}]`;
  const hookSrc = readFileSync(resolve(SRC, owner), "utf8");
  check(
    hookSrc.includes(selector),
    `${owner} no longer queries ${selector}`
  );
  check(
    foundAttrs.has(attr),
    `no element in src/ carries data-plateau-${attr}, but ${owner} queries ` +
      `for it — the timeline step would silently no-op`
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
    `\n  animejs importers: ${animeImporters.join(", ")}` +
    `\n  anime targets   : ${taggedNodes} node(s), none owned by Framer Motion` +
    `\n  attrs matched   : ${[...foundAttrs].map((a) => `data-plateau-${a}`).join(", ")}\n`
);
