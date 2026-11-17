// Shared helpers for the native (no-Docker) dev scripts. Node ≥ 20, no dependencies.
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const BACKEND = path.join(ROOT, "backend");
export const FRONTEND = path.join(ROOT, "frontend");
export const IS_WIN = process.platform === "win32";
export const VENV_PY = path.join(BACKEND, ".venv", IS_WIN ? "Scripts/python.exe" : "bin/python");

const COLORS = { api: 36, worker: 35, beat: 34, web: 32, setup: 33 };

export function log(name, msg) {
  const c = COLORS[name] ?? 37;
  for (const line of String(msg).split(/\r?\n/)) if (line.trim()) console.log(`\x1b[${c}m${name.padEnd(6)}\x1b[0m │ ${line}`);
}

export function fail(msg) {
  console.error(`\n\x1b[31m✗ ${msg}\x1b[0m\n`);
  process.exit(1);
}

export function requireVenv() {
  if (!existsSync(VENV_PY)) fail("Backend environment missing. Run `npm run setup` first.");
}

/** Run to completion with inherited stdio; exit on failure. */
export function runSync(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: "inherit", shell: false, ...opts });
  if (r.status !== 0) fail(`${path.basename(cmd)} ${args.join(" ")} failed (exit ${r.status ?? r.error?.message})`);
}

/** Long-running child with prefixed output. */
export function start(name, cmd, args, opts = {}) {
  const child = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"], shell: false, ...opts });
  child.stdout.on("data", (d) => log(name, d));
  child.stderr.on("data", (d) => log(name, d));
  child.on("exit", (code, signal) => log(name, `exited (${signal ?? code})`));
  return child;
}

/** Kill a process tree (uvicorn --reload and next dev spawn grandchildren). */
export function killTree(child) {
  if (!child?.pid || child.exitCode !== null) return;
  if (IS_WIN) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else {
    try { process.kill(-child.pid, "SIGTERM"); } catch { child.kill("SIGTERM"); }
  }
}

/** True if something already accepts TCP connections on host:port. */
function inUse(port, host) {
  return new Promise((resolve) => {
    const sock = net.connect({ port, host });
    const done = (v) => { sock.destroy(); resolve(v); };
    sock.setTimeout(500, () => done(false));
    sock.once("connect", () => done(true)).once("error", () => done(false));
  });
}

function canListen(port, host) {
  return new Promise((resolve) => {
    const srv = net.createServer().once("error", () => resolve(false)).once("listening", () => srv.close(() => resolve(true)));
    srv.listen(port, host);
  });
}

// A bind test alone is not enough on Windows: binding 0.0.0.0 can succeed while another
// process already listens on the same port (e.g. on [::]), and Next.js then dies with
// EADDRINUSE. So also probe for a live listener on both loopbacks.
export async function portFree(port) {
  if ((await inUse(port, "127.0.0.1")) || (await inUse(port, "::1"))) return false;
  return canListen(port, "0.0.0.0");
}

/** First free port starting at `preferred`, stepping by `step`. */
export async function pickPort(preferred, step = 1, tries = 20) {
  for (let i = 0, p = preferred; i < tries; i++, p += step) if (await portFree(p)) return p;
  fail(`No free port found near ${preferred}`);
}

export async function waitForHttp(url, timeoutMs = 90_000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try {
      const r = await fetch(url);
      if (r.status < 500) return true;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 700));
  }
  return false;
}
