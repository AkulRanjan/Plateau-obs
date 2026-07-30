/**
 * Offline check.
 *
 * The demo runs at a venue, on venue wifi, possibly with none. The build must
 * therefore make ZERO network requests: no CDN script, no external stylesheet,
 * no remote font, no analytics. The draft loaded Space Grotesk and IBM Plex Mono
 * from Google Fonts, which is exactly the kind of dependency that turns into a
 * fallback-serif demo in front of judges.
 *
 * This scans the built output for external URLs and fails on anything
 * fetchable. Run it after a build.
 *
 *   npm run offline
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, extname, join, relative, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const DIST = resolve(HERE, "../dist");

/**
 * URLs that appear in the bundle but are never fetched.
 *
 * - XML namespace URIs are identifiers. SVG and MathML will not resolve them.
 * - react.dev/errors is a documentation pointer inside a thrown error's message.
 *
 * Anything not on this list is treated as a real remote dependency.
 */
const INERT = [
  /^https?:\/\/www\.w3\.org\//,
  /^https?:\/\/react\.dev\/errors/,
];

/** Text formats worth scanning. Fonts and images cannot carry a fetch. */
const TEXTUAL = new Set([".js", ".mjs", ".css", ".html", ".json", ".map", ".svg"]);

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

let files;
try {
  files = walk(DIST);
} catch {
  console.error(
    `\noffline CHECK FAILED — no dist/ directory. Run \`npm run build\` first.\n`
  );
  process.exit(1);
}

const findings = new Map();
let scanned = 0;

for (const file of files) {
  if (!TEXTUAL.has(extname(file))) continue;
  scanned += 1;
  const text = readFileSync(file, "utf8");
  for (const url of text.match(/https?:\/\/[^\s"'`)\\]+/g) ?? []) {
    if (INERT.some((re) => re.test(url))) continue;
    const key = url.replace(/[.,;]+$/, "");
    if (!findings.has(key)) findings.set(key, relative(DIST, file));
  }
}

// Also catch the specific pattern that bit the draft: an @import or <link> to a
// remote stylesheet, which a bare URL scan could miss if it were relative.
const cssFiles = files.filter((f) => extname(f) === ".css");
const remoteImports = [];
for (const file of cssFiles) {
  const text = readFileSync(file, "utf8");
  for (const m of text.matchAll(/@import\s+url\(\s*['"]?(https?:)?\/\//g)) {
    remoteImports.push(`${relative(DIST, file)}: ${m[0].trim()}`);
  }
}

const fonts = files.filter((f) => /\.(woff2?|ttf|otf)$/.test(f)).length;

if (findings.size || remoteImports.length) {
  console.error(`\noffline CHECK FAILED — the build reaches the network:\n`);
  for (const [url, file] of findings) console.error(`  · ${url}  (${file})`);
  for (const imp of remoteImports) console.error(`  · remote @import — ${imp}`);
  console.error("");
  process.exit(1);
}

console.log(
  `\noffline check OK` +
    `\n  scanned      : ${scanned} text asset(s) of ${files.length} in dist/` +
    `\n  external refs: none fetchable (w3.org namespaces and react.dev error` +
    ` docs ignored — neither is requested)` +
    `\n  fonts        : ${fonts} bundled locally, no Google Fonts\n`
);
