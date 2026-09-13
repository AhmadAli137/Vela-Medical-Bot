# Deployment

Current entrypoints and synchronization are described in the [app guide](APP_GUIDE.md). The native viewer now uses the reference scene and shared local session when opened from the app; the original primitive model remains an explicitly labeled benchmark.

## Public 3D demo on Vercel

Live production: **https://vela-medical-bot.vercel.app**. Source: **https://github.com/AhmadAli137/Vela-Medical-Bot** (private repository). The Vercel project is connected to GitHub; pushes to `main` trigger production builds. The initial production deployment reached `Ready` on September 12, 2026, and the public URL returned HTTP 200 without sign-in.

The geometry and physical pickup correction (`ce06e0d`) deployed successfully on September 13, 2026. Anonymous Chrome verified the production joint motion, low/high travel, contact pickup, sustained hold and gravity release with zero browser or network errors. [Measured result](../artifacts/vercel-browser-check.json).

The public build runs the reference robot's MuJoCo 3.13.0 physics inside the browser using the official `@mujoco/mujoco` WebAssembly package. It includes four GLBs, the estimated MJCF model, 46 synchronized bodies (27 robot, two free objects and 17 passive blind parts), four camera views, a visual mapping prototype, and contact-driven pickup, delivery and blind-control demonstrations. The phone starts on a visible 35 mm rest; there is no weld or kinematic object attachment. Each visitor has an independent, ephemeral simulation. No Python server, shared task database, paid model API, robot connection, or recorded-pose playback is required for this view.

The full staff/patient/fleet/research workspace remains the separate local Python application described below. The public build opens the 3D view and explains this boundary instead of exposing disconnected operational controls.

Import this repository into Vercel with its repository root as the project root. The checked-in `vercel.json` selects Vite, installs with `npm --prefix apps/web ci`, builds with `npm --prefix apps/web run build:public`, and publishes `apps/web/dist`. Build assets are copied from `assets/simulation/`; the WASM engine is bundled from the pinned npm dependency. The official engine's embind JavaScript bindings generate functions at startup, so this public demo's CSP permits `unsafe-eval` as well as WebAssembly compilation. Scripts and connections remain restricted to same-origin assets. The separate Python workspace retains its original, stricter script policy.

```powershell
npm --prefix apps/web ci
npm --prefix apps/web run build:public
npm --prefix apps/web run preview -- --port 4173
```

The public build replaces `apps/web/dist`. Run `npm --prefix apps/web run build` afterward to restore the local dashboard bundle served by FastAPI. Vercel builds its own deployment independently. Do not serve the public WASM bundle through an older local CSP that lacks `wasm-unsafe-eval`.

Vite computes one revision hash from all four GLBs and both physics metadata files. Their fetch URLs share that revision, so an ordinary page reload after deployment cannot mix a cached old room or robot with the new physics topology.

`.vercelignore` restricts CLI uploads to the frontend build inputs and authored GLBs. `.gitignore` excludes provider credentials, `.env.local`, `.vercel`, local databases, raw source media and copyrighted reference photographs. The source repository retains the full implementation and the separately licensed CC0 material provenance.

Browser-engine regressions: `node --test --test-isolation=none tests/browser-physics-wasm.mjs` from `apps/web` (Node 24). See [current validation](TESTING.md) for native/WASM parity, contact pickup/release, independent lift motion and browser checks. Hardware geometry, inertias and controls remain unverified estimates.

## Full local workspace

The validated target is a single local Windows process with Python 3.12, Node 24 and a browser. The frontend production build is served by FastAPI. SQLite persists to `runtime/vela.sqlite3`; training data goes to a separate `runtime/learning` registry. No hospital deployment was performed.

Run `scripts/setup.ps1` once and `scripts/run.ps1` afterward. For a manual setup:

```powershell
py -3.12 -m venv .venv
uv pip install --python .venv/Scripts/python.exe --cache-dir .cache/uv -r requirements.lock
npm --prefix apps/web ci
npm --prefix apps/web run build
.\.venv\Scripts\python.exe -m uvicorn services.app:app --host 127.0.0.1 --port 8000 --workers 1
```

The setup requires network access for dependencies. Within this managed environment, dependency downloads and pytest temporary directories required sandbox elevation. Outside it, normal user permissions should suffice. The application reads process environment variables; `.env.example` is documentation, not an automatically loaded secret file.

Local demo mode rejects non-loopback clients and permits role switching. For access-control testing, set `VELA_DEMO_MODE=0`, provision independent strong `VELA_<ROLE>_TOKEN` values, and serve behind a properly configured TLS reverse proxy matching `VELA_PUBLIC_ORIGIN`. Cookies require HTTPS outside demo mode. This is a prototype token boundary, not hospital SSO. All operational adapters remain synthetic even in token mode.

`infra/Dockerfile` provides a nonroot, single-worker Linux build recipe. It has not been built/tested here. Offscreen MuJoCo graphics require EGL/OpenGL support appropriate to the deployment host. Do not claim container portability from the verified Windows run.

Production prerequisites: SSO and scoped identities; managed device certificates; hardware-backed robot identity and vendor watchdog; encrypted storage and backups; segregated network/egress; retention/deletion jobs; centralized immutable audit; incident response; institution-approved integrations and monitoring. Moving to a hospital is not a matter of changing an environment flag.

## Preventing stale builds

Both npm build modes now check matching native/public XML, descriptors, body bindings and trajectory model hashes before compilation. A build receipt records the inputs and output hashes; inputs changing during a build invalidate the receipt. Local launchers check that receipt and rebuild a stale or public-mode bundle as a local bundle. They also reject an already-running backend with an older source revision, so it must be restarted before opening the updated app.

The native visual cache is keyed by source GLBs, physics XML, importer code and MuJoCo version, with integrity hashes for its generated files. Both Python and browser physics are pinned to MuJoCo 3.13.0. Run `python -m sim.sync_check --build-mode local --output artifacts/scene-sync.json` to verify the checked-out source, generated physics, shared trajectories, visual body bindings and local build. The checker reports the absence of an original Blender source-build receipt rather than claiming that provenance was verified.
