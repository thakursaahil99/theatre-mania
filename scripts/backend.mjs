// Run a Python module inside backend/.venv:  node scripts/backend.mjs -m pytest -q
import { BACKEND, VENV_PY, requireVenv, runSync } from "./lib.mjs";

requireVenv();
runSync(VENV_PY, process.argv.slice(2), { cwd: BACKEND, env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" } });
