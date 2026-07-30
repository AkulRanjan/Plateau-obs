/**
 * Visual + runtime check, in a real browser.
 *
 * The other checks are static or server-rendered. They cannot see a console
 * error, an SVG attribute that Framer Motion overwrites with `undefined`, a
 * label that collides with another label, or a demo that silently fails to
 * auto-start. Every one of those shipped past a green `npm run check` and was
 * only caught by rendering the page and looking at it.
 *
 * So this drives headless Chrome over CDP on WALL-CLOCK time, waits for the run
 * to reach its halt, captures a screenshot, and reports:
 *
 *   - every console error and uncaught exception
 *   - every failed network request
 *   - whether the run actually reached the trip
 *   - whether the telemetry rows are really visible (opacity, not just present)
 *   - overlapping text nodes inside the SVG charts
 *
 * NOTE ON --virtual-time-budget: do not use it here. It fast-forwards timers but
 * leaves requestAnimationFrame animations frozen at their initial keyframe, so
 * every Framer Motion element screenshots at opacity 0 and the whole report is
 * a lie. Real time only.
 *
 *   npm run visual              # console view
 *   npm run visual -- --split   # split-screen view
 *
 * Requires a dev or preview server on --url (default http://localhost:5173)
 * and Chrome started with --remote-debugging-port=9222. `npm run visual` starts
 * Chrome itself if it is not already listening.
 */
import { writeFileSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = resolve(HERE, "../.visual");

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const hit = args.find((a) => a.startsWith(`--${name}=`));
  return hit ? hit.split("=").slice(1).join("=") : fallback;
};
const has = (name) => args.includes(`--${name}`);

const URL_ = flag("url", "http://localhost:5173/");
const WAIT_MS = Number(flag("wait", "20000"));
const SPLIT = has("split");
const WIDTH = Number(flag("width", "1920"));
const HEIGHT = Number(flag("height", SPLIT ? "1500" : "2600"));
const CDP = flag("cdp", "http://127.0.0.1:9222");

// --- make sure a debuggable Chrome is listening ---------------------------
async function chromeUp() {
  try {
    const r = await fetch(`${CDP}/json/version`);
    return r.ok;
  } catch {
    return false;
  }
}

let spawned = null;
if (!(await chromeUp())) {
  const bin =
    process.env.CHROME_BIN ||
    ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"].find(
      Boolean
    );
  spawned = spawn(
    bin,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-sandbox",
      "--hide-scrollbars",
      "--remote-debugging-port=9222",
      `--user-data-dir=${OUT_DIR}/chrome-profile`,
    ],
    { stdio: "ignore", detached: true }
  );
  spawned.unref();
  for (let i = 0; i < 15; i++) {
    if (await chromeUp()) break;
    await new Promise((r) => setTimeout(r, 700));
  }
  if (!(await chromeUp())) {
    console.error(
      `\nvisual CHECK FAILED — could not start Chrome with remote debugging.\n` +
        `Set CHROME_BIN, or start it yourself:\n` +
        `  google-chrome --headless=new --remote-debugging-port=9222 \\\n` +
        `    --user-data-dir=/tmp/plateau-chrome\n`
    );
    process.exit(1);
  }
}

// --- connect ---------------------------------------------------------------
const target = await (
  await fetch(`${CDP}/json/new?${encodeURIComponent(URL_)}`, { method: "PUT" })
).json();

const ws = new WebSocket(target.webSocketDebuggerUrl);
let msgId = 0;
const pending = new Map();
const consoleErrors = [];
const failedRequests = [];

const send = (method, params = {}) =>
  new Promise((res) => {
    const id = ++msgId;
    pending.set(id, res);
    ws.send(JSON.stringify({ id, method, params }));
  });

ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m.result);
    pending.delete(m.id);
    return;
  }
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") {
    consoleErrors.push(
      m.params.args.map((a) => a.value ?? a.description ?? "?").join(" ")
    );
  }
  if (m.method === "Runtime.exceptionThrown") {
    const d = m.params.exceptionDetails;
    consoleErrors.push("EXCEPTION: " + (d.exception?.description ?? d.text));
  }
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error") {
    const t = m.params.entry.text;
    if (m.params.entry.source === "network") failedRequests.push(t);
    else consoleErrors.push(t);
  }
});

await new Promise((r) => ws.addEventListener("open", r));
await send("Runtime.enable");
await send("Log.enable");
await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", {
  width: WIDTH,
  height: HEIGHT,
  deviceScaleFactor: 1,
  mobile: false,
});
await send("Page.navigate", { url: URL_ });
await new Promise((r) => setTimeout(r, 1500));

if (SPLIT) {
  await send("Runtime.evaluate", {
    expression: `[...document.querySelectorAll('[role=tab]')].find(b => b.textContent.includes('Split'))?.click()`,
  });
}

await new Promise((r) => setTimeout(r, WAIT_MS));

// --- probe the live DOM ----------------------------------------------------
const probe = await send("Runtime.evaluate", {
  returnByValue: true,
  expression: `(() => {
    const txt = document.body.innerText;

    const rows = [...document.querySelectorAll('[class*="grid-cols-[26px_1fr_auto]"]')];
    const rowOpacity = rows.map(r => Number(getComputedStyle(r).opacity));

    // Any element that is present but effectively invisible is worth flagging:
    // it usually means an animation never completed.
    const invisible = [...document.querySelectorAll('body *')].filter(el => {
      const s = getComputedStyle(el);
      if (s.display === 'none' || s.visibility === 'hidden') return false;
      if (Number(s.opacity) > 0.05) return false;
      if (el.hasAttribute('aria-hidden')) return false;
      return (el.textContent || '').trim().length > 0;
    }).slice(0, 8).map(el => el.tagName + '.' + (el.className || '').toString().slice(0, 40));

    // Overlapping SVG text, which is how label collisions show up.
    const collisions = [];
    for (const svg of document.querySelectorAll('svg')) {
      const texts = [...svg.querySelectorAll('text')].filter(t => (t.textContent||'').trim());
      for (let i = 0; i < texts.length; i++) {
        for (let j = i + 1; j < texts.length; j++) {
          const a = texts[i].getBoundingClientRect();
          const b = texts[j].getBoundingClientRect();
          if (a.width === 0 || b.width === 0) continue;
          const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
          const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
          if (ox > 2 && oy > 2) {
            collisions.push(
              texts[i].textContent.trim() + ' <-> ' + texts[j].textContent.trim()
            );
          }
        }
      }
    }

    // Horizontal overflow: the page body must never scroll sideways.
    const overflowX = document.documentElement.scrollWidth > window.innerWidth + 1;

    return {
      reachedTrip: /OPEN · plateau detected/.test(txt),
      turnPill: (txt.match(/TURN\\s*\\n?\\s*(\\d+|—)\\s*\\/\\s*(\\d+)/) || [])[0] || null,
      telemetryRows: rows.length,
      telemetryVisible: rowOpacity.filter(o => o > 0.9).length,
      invisibleWithText: invisible,
      svgTextCollisions: [...new Set(collisions)],
      overflowX,
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      bigNumbers: (txt.match(/[\\d]{1,3}(,[\\d]{3})+/g) || []).slice(0, 6),
    };
  })()`,
});

const d = probe.result.value;

mkdirSync(OUT_DIR, { recursive: true });
const shotPath = resolve(OUT_DIR, SPLIT ? "split.png" : "console.png");
const shot = await send("Page.captureScreenshot", {
  format: "png",
  captureBeyondViewport: true,
});
writeFileSync(shotPath, Buffer.from(shot.data, "base64"));

await send("Page.close");
ws.close();

// --- verdict ---------------------------------------------------------------
const problems = [];
const check = (ok, msg) => {
  if (!ok) problems.push(msg);
};

check(consoleErrors.length === 0, `console errors:\n      ${consoleErrors.slice(0, 12).join("\n      ")}`);
check(
  failedRequests.length === 0,
  `failed requests:\n      ${failedRequests.slice(0, 8).join("\n      ")}`
);
check(
  d.reachedTrip,
  "the run never reached 'OPEN · plateau detected' — auto-play or the halt is broken"
);
check(
  d.svgTextCollisions.length === 0,
  `overlapping SVG labels:\n      ${d.svgTextCollisions.join("\n      ")}`
);
check(
  d.invisibleWithText.length === 0,
  `elements present but invisible (an animation likely never finished):\n      ${d.invisibleWithText.join("\n      ")}`
);
check(!d.overflowX, `page scrolls horizontally (${d.scrollWidth}px > ${d.innerWidth}px)`);
if (!SPLIT) {
  check(
    d.telemetryRows > 0 && d.telemetryRows === d.telemetryVisible,
    `${d.telemetryVisible}/${d.telemetryRows} telemetry rows are visible`
  );
}

console.log(
  `\n${SPLIT ? "split-screen" : "console"} view` +
    `\n  url            : ${URL_}` +
    `\n  screenshot     : ${shotPath}` +
    `\n  turn           : ${d.turnPill ?? "?"}` +
    `\n  reached trip   : ${d.reachedTrip}` +
    `\n  telemetry rows : ${d.telemetryVisible}/${d.telemetryRows} visible` +
    `\n  numbers on page: ${d.bigNumbers.join(", ") || "none"}` +
    `\n  console errors : ${consoleErrors.length}` +
    `\n  failed requests: ${failedRequests.length}`
);

if (problems.length) {
  console.error(`\nvisual CHECK FAILED — ${problems.length} problem(s):\n`);
  for (const p of problems) console.error(`  · ${p}`);
  console.error("");
  process.exit(1);
}

console.log(`\nvisual check OK\n`);
process.exit(0);
