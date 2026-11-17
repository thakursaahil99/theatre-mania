// Native dev runner (no Docker):  npm run dev
// Starts the API (hot reload), Celery worker + scheduler and the Next.js dev server with
// prefixed logs. Picks free ports automatically (prefers API 8000, web 3000; override with
// API_PORT / WEB_PORT) and wires the URLs between them. Ctrl+C stops everything.
import { mkdirSync } from "node:fs";
import path from "node:path";

import { BACKEND, FRONTEND, IS_WIN, VENV_PY, killTree, log, pickPort, requireVenv, runSync, start, waitForHttp } from "./lib.mjs";

requireVenv();

const apiPort = await pickPort(Number(process.env.API_PORT ?? 8000));
const webPort = await pickPort(Number(process.env.WEB_PORT ?? 3000));
const apiUrl = `http://127.0.0.1:${apiPort}`; // IPv4 explicitly: Node resolves "localhost" to ::1 first
const webUrl = `http://localhost:${webPort}`;

const backendEnv = {
  ...process.env,
  PYTHONUNBUFFERED: "1",
  PYTHONIOENCODING: "utf-8",
  // Native file events don't fire reliably on some Windows drives; polling makes --reload dependable.
  WATCHFILES_FORCE_POLLING: "true",
  FRONTEND_URL: webUrl,
  CORS_ORIGINS: `${webUrl},http://127.0.0.1:${webPort}`,
  API_PUBLIC_URL: apiUrl,
  GOOGLE_REDIRECT_URI: `${webUrl}/api/v1/auth/google/callback`,
};
const detached = !IS_WIN; // own process group on POSIX so the whole tree can be stopped

mkdirSync(path.join(BACKEND, "data"), { recursive: true });
log("api", "applying migrations …");
runSync(VENV_PY, ["-m", "alembic", "upgrade", "head"], { cwd: BACKEND, env: backendEnv });

const procs = [
  start("api", VENV_PY, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(apiPort),
    "--reload", "--reload-dir", "app", "--timeout-graceful-shutdown", "5"], { cwd: BACKEND, env: backendEnv, detached }),
  start("worker", VENV_PY, ["-m", "celery", "-A", "app.workers.celery_app", "worker", "--pool=solo",
    "-Q", "transcode,default", "--loglevel", "info"], { cwd: BACKEND, env: backendEnv, detached }),
  start("beat", VENV_PY, ["-m", "celery", "-A", "app.workers.celery_app", "beat", "--loglevel", "warning",
    "--schedule", path.join("data", "celerybeat-schedule")], { cwd: BACKEND, env: backendEnv, detached }),
  start("web", process.execPath, [path.join(FRONTEND, "node_modules", "next", "dist", "bin", "next"), "dev", "-p", String(webPort)], {
    cwd: FRONTEND,
    env: { ...process.env, API_INTERNAL_URL: apiUrl, NEXT_PUBLIC_SITE_URL: webUrl, NEXT_TELEMETRY_DISABLED: "1" },
    detached,
  }),
];

let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  log("setup", "stopping …");
  procs.forEach(killTree);
  setTimeout(() => process.exit(code), 500);
}
process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
procs.forEach((p) => p.on("exit", (code) => !stopping && code !== 0 && code !== null && log("setup", "a process crashed; see its log above")));

const [apiUp, webUp] = await Promise.all([waitForHttp(`${apiUrl}/healthz`), waitForHttp(`${webUrl}/login`, 180_000)]);
console.log(`
\x1b[32m${apiUp && webUp ? "✓ Theatre Mania is running" : "⚠ Something didn't start; check the logs above"}\x1b[0m
  App        ${webUrl}
  API docs   ${apiUrl}/api/v1/docs
  Ctrl+C to stop
`);
