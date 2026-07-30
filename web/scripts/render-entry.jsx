/**
 * Render check.
 *
 * Server-renders the real App and asserts the things a `vite build` cannot see:
 * that it renders at all, and that the backdrop-filter budget is respected.
 *
 * The blur budget is the perf rule most likely to be broken by a later edit —
 * `blur` is one prop away on every panel — so it is asserted here rather than
 * left to a comment in GlassPanel.
 *
 *   npm run render
 */
import { renderToString } from "react-dom/server";
import App from "../src/App.jsx";

/** StatusBar and Hero. Nothing else may layer backdrop-filter over the aurora. */
const MAX_BLUR_SURFACES = 2;

const html = renderToString(<App />);

const problems = [];
const check = (ok, msg) => {
  if (!ok) problems.push(msg);
};

const count = (re) => (html.match(re) || []).length;

const blurPanels = count(/pl-panel--blur/g);
const totalPanels = count(/class="pl-panel/g);
const auroraBlobs = count(/pl-aurora-blob pl-aurora-blob--/g);

check(html.length > 1000, `suspiciously short render (${html.length} chars)`);
check(html.includes("PLATEAU"), "brand did not render");
check(
  html.includes("data-plateau-pill"),
  "state pill missing — the Anime.js trip timeline targets it by this attribute"
);
check(html.includes("pl-aurora"), "aurora did not render");

check(
  blurPanels <= MAX_BLUR_SURFACES,
  `${blurPanels} panels use backdrop-filter; the budget is ${MAX_BLUR_SURFACES} ` +
    `(StatusBar and Hero). Stacked blur over the aurora is what drops frames ` +
    `on integrated GPUs — solidify the extra panels instead.`
);

check(
  auroraBlobs === 3,
  `aurora has ${auroraBlobs} gradient layers; the cap is 3`
);

// A CSS filter on a continuously-animating element is the other expensive
// mistake. The aurora must not carry one.
check(
  !/pl-aurora[^"]*"[^>]*style="[^"]*filter:/.test(html),
  "the aurora carries an inline CSS filter — radial falloff only, no blur pass"
);

if (problems.length) {
  console.error(`\nrender CHECK FAILED — ${problems.length} problem(s):\n`);
  for (const p of problems) console.error(`  · ${p}`);
  console.error("");
  process.exit(1);
}

console.log(
  `\nrender check OK` +
    `\n  html            : ${html.length} chars` +
    `\n  panels          : ${totalPanels} (${blurPanels} blurred, budget ${MAX_BLUR_SURFACES})` +
    `\n  aurora layers   : ${auroraBlobs} (cap 3)\n`
);
