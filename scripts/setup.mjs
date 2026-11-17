// One-time native setup (no Docker):  npm run setup  [-- --force]
//  1. Python 3.12 venv in backend/.venv via uv, with backend dependencies
//  2. Portable FFmpeg in backend/.tools/ffmpeg (Windows; checksum-verified), or FFmpeg on PATH
//  3. backend/.env from backend/.env.native.example (random JWT secret, FFmpeg paths)
//  4. Database migrations, frontend dependencies
import crypto from "node:crypto";
import { createWriteStream, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { spawnSync } from "node:child_process";

import { BACKEND, FRONTEND, IS_WIN, VENV_PY, fail, log, runSync } from "./lib.mjs";

const force = process.argv.includes("--force");
const TOOLS = path.join(BACKEND, ".tools");
const FFMPEG_ZIP = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip";

// ---------------------------------------------------------------- 1. python
const uv = spawnSync("uv", ["--version"], { encoding: "utf8" });
if (uv.status !== 0) {
  fail("`uv` not found. Install it (one line, no admin rights): https://docs.astral.sh/uv/getting-started/installation/");
}
log("setup", `using ${uv.stdout.trim()}`);
if (!existsSync(VENV_PY)) {
  log("setup", "creating Python 3.12 environment in backend/.venv …");
  runSync("uv", ["venv", "--python", "3.12", path.join(BACKEND, ".venv")]);
}
log("setup", "installing backend dependencies …");
runSync("uv", ["pip", "install", "--python", VENV_PY, "-q", "-r", "requirements-dev.txt"], { cwd: BACKEND });

// ---------------------------------------------------------------- 2. ffmpeg
function findLocalFfmpeg() {
  const dir = path.join(TOOLS, "ffmpeg");
  if (!existsSync(dir)) return null;
  const stack = [dir];
  while (stack.length) {
    const d = stack.pop();
    for (const name of readdirSync(d)) {
      const p = path.join(d, name);
      if (statSync(p).isDirectory()) stack.push(p);
      else if (name === (IS_WIN ? "ffmpeg.exe" : "ffmpeg")) {
        const probe = path.join(d, IS_WIN ? "ffprobe.exe" : "ffprobe");
        if (existsSync(probe)) return { ffmpeg: p, ffprobe: probe };
      }
    }
  }
  return null;
}

async function downloadFfmpeg() {
  mkdirSync(TOOLS, { recursive: true });
  const zip = path.join(TOOLS, "ffmpeg.zip");
  const expected = (await (await fetch(`${FFMPEG_ZIP}.sha256`)).text()).trim().split(/\s+/)[0].toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(expected)) fail("Could not fetch the FFmpeg checksum; aborting download.");
  const sha256 = (file) => crypto.createHash("sha256").update(readFileSync(file)).digest("hex");

  if (existsSync(zip) && sha256(zip) === expected) {
    log("setup", "reusing previously downloaded FFmpeg archive (checksum verified)");
  } else {
    log("setup", `downloading portable FFmpeg (~100 MB) from ${new URL(FFMPEG_ZIP).host} …`);
    const res = await fetch(FFMPEG_ZIP);
    if (!res.ok || !res.body) fail(`FFmpeg download failed: HTTP ${res.status}`);
    await pipeline(Readable.fromWeb(res.body), createWriteStream(zip));
    const actual = sha256(zip);
    if (actual !== expected) {
      rmSync(zip, { force: true });
      fail(`FFmpeg checksum mismatch (expected ${expected}, got ${actual}); download discarded.`);
    }
    log("setup", "checksum verified");
  }

  log("setup", "extracting …");
  const dest = path.join(TOOLS, "ffmpeg");
  rmSync(dest, { recursive: true, force: true });
  mkdirSync(dest, { recursive: true });
  // Use Windows' own bsdtar: a Git-for-Windows GNU tar on PATH misreads "E:\..." as host:path.
  const bsdtar = path.join(process.env.SystemRoot ?? "C:\\Windows", "System32", "tar.exe");
  if (existsSync(bsdtar)) runSync(bsdtar, ["-xf", zip, "-C", dest]);
  else runSync("powershell.exe", ["-NoProfile", "-Command", `Expand-Archive -LiteralPath '${zip}' -DestinationPath '${dest}' -Force`]);
  rmSync(zip, { force: true });
}

let ff = findLocalFfmpeg();
if (!ff) {
  const onPath = spawnSync("ffmpeg", ["-version"], { stdio: "ignore" }).status === 0
    && spawnSync("ffprobe", ["-version"], { stdio: "ignore" }).status === 0;
  if (onPath) ff = { ffmpeg: "ffmpeg", ffprobe: "ffprobe" };
  else if (IS_WIN) {
    await downloadFfmpeg();
    ff = findLocalFfmpeg();
  } else {
    log("setup", "⚠ FFmpeg not found. Install it (macOS: brew install ffmpeg · Debian/Ubuntu: sudo apt install ffmpeg) to transcode videos.");
  }
}
if (ff) log("setup", `ffmpeg: ${ff.ffmpeg}`);

// ---------------------------------------------------------------- 3. backend/.env
const envPath = path.join(BACKEND, ".env");
if (!existsSync(envPath) || force) {
  let env = readFileSync(path.join(BACKEND, ".env.native.example"), "utf8");
  env = env.replace("JWT_SECRET=__generated_by_setup__", `JWT_SECRET=${crypto.randomBytes(36).toString("base64url")}`);
  if (ff) {
    const slash = (p) => p.replaceAll("\\", "/");
    env = env.replace(/^FFMPEG_BIN=.*$/m, `FFMPEG_BIN=${slash(ff.ffmpeg)}`).replace(/^FFPROBE_BIN=.*$/m, `FFPROBE_BIN=${slash(ff.ffprobe)}`);
  }
  writeFileSync(envPath, env);
  log("setup", `wrote backend/.env${force ? " (--force)" : ""}`);
} else {
  log("setup", "backend/.env exists; keeping it (re-run with --force to regenerate for native mode)");
}

// ---------------------------------------------------------------- 4. db + frontend
mkdirSync(path.join(BACKEND, "data"), { recursive: true });
log("setup", "applying database migrations …");
runSync(VENV_PY, ["-m", "alembic", "upgrade", "head"], { cwd: BACKEND });

if (!existsSync(path.join(FRONTEND, "node_modules", "next"))) {
  log("setup", "installing frontend dependencies …");
  runSync(IS_WIN ? "npm.cmd" : "npm", ["install", "--no-audit", "--no-fund"], { cwd: FRONTEND, shell: IS_WIN });
}

console.log(`
\x1b[32m✓ Setup complete.\x1b[0m

  npm run dev                                   start API, worker, scheduler and web app
  npm run seed -- --only "trip to the moon" --publish   import a free film
  npm run seed -- --dry-run                     preview all 20 public-domain matches

  Add TMDB_READ_TOKEN to backend/.env for posters, cast, trailers and the TMDB rows.
`);
