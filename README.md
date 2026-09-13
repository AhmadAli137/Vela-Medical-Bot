# Vela — patient environment agent

**[Open the live 3D simulation](https://vela-medical-bot.vercel.app)** — the public demo runs real MuJoCo physics in your browser, including arm and shoulder-lift motion and a contact-driven phone pickup from a raised rest. The complete local Python workspace is included in this repository. See [deployment details](docs/DEPLOYMENT.md).

A runnable research prototype for non-clinical patient requests and hospital room operations. Open **http://127.0.0.1:8000/#simulation** for the reference-based hospital-room demo: a detailed Blender-authored room with a Bracket Bot visual approximation, actual MuJoCo dynamics, and streamed body poses rendered in Three.js.

The room uses architectural observations from inspected official Stanford/UCLA photographs and nine CC0 material maps. The robot uses the supplied handout and three inspected videos: **27 robot bodies, 25 estimated actuators, and one freely moving phone**. MuJoCo computes dynamics and contacts; Three.js displays the authored meshes at those body poses. Geometry, inertias, gains and friction are estimates. The pickup is a fixed simulated fixture, not a vendor-verified robot skill or learned VLA policy. See [reference sources and asset provenance](docs/REFERENCE_UPGRADE.md) and [validation evidence](docs/TESTING.md).

Vela also remembers room snapshots, compares semantic desired states, plans permitted changes, applies deterministic safety checks, changes a **synthetic** room, and verifies the result. It includes a correction-data learning workflow.

**No real robot, Quest headset, hospital system or patient data is connected.** The simulator is not hardware accurate. The learned baseline is a small synthetic state-feature regression model, not a trained vision-language-action model.

## Run locally

For the already installed demo, double-click **[Open Simulation.cmd](Open%20Simulation.cmd)**. It starts the local server if needed and opens the interactive room at **http://127.0.0.1:8000/#simulation**.

Windows: Python 3.12 and Node 24 were used.

```powershell
.\scripts\setup.ps1
.\scripts\run.ps1
```

Open **http://127.0.0.1:8000/#simulation** for the browser simulation. The patient experience, room operations, robot/fleet, and research studio share its backend. Local role switching is for synthetic demonstrations only. The patient view cannot contact hospital staff; urgent requests explicitly direct the user to their existing call pathway.

For development, run the API and Vite in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn services.app:app --host 127.0.0.1 --port 8000
npm --prefix apps/web run dev
```

## Exercise the implementation

```powershell
.\.venv\Scripts\python.exe -m scripts.run_demo
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.cache/tests-local
.\.venv\Scripts\python.exe -m sim benchmark --episodes 24 --seed 7 --output artifacts/simulation
.\.venv\Scripts\python.exe -m sim render --output artifacts/simulation
.\.venv\Scripts\python.exe -m sim viewer
.\.venv\Scripts\python.exe -m ml demo --output artifacts/learning
npm --prefix apps/web run build
```

The demo script runs phone placement, physio preparation, low-confidence refusal followed by synthetic correction recording, and clinical escalation. It writes `artifacts/demo-report.json`. It reports zero real robot actions and zero live hospital messages.

In the browser, **Vertical travel** moves the two shoulder carriages independently and extends the hands from approximately 0.13 m to 1.72 m above the floor. **Pick up phone** approaches the 35 mm raised rest, closes the fingers, lifts the free body about 23 cm and holds it through frictional contact. **Release phone** opens the fingers so gravity drops it. The head stays fixed to the mast. Reset between demonstrations. The constrained planar base does not simulate or validate two-wheel balancing.

The original surrogate remains available through `python -m sim viewer`, which opens the native MuJoCo window: drag to orbit, wheel to zoom, Space to pause, R to reset, C to cycle cameras. The detailed browser scene is separate from that original primitive viewer.

To reproduce the authored visual assets and render, install Blender 5.1 and put its executable on `PATH`:

```powershell
blender --background --factory-startup --python scripts/build_reference_visuals.py -- --render
```

Optional PDF inspection uses PyMuPDF, installed separately with `uv pip install --python .venv/Scripts/python.exe pymupdf`. It is not required to view the built demo. See [current test results](docs/TESTING.md) for native physics, browser WebAssembly, API and visual-asset checks.

## Repository

```text
apps/web/          React + TypeScript: four application surfaces
services/         FastAPI gateway, routing, planning, critique, world model, safety, audit
robot/            Reported capability manifest, fail-closed vendor boundary, mock adapter
sim/              Reference MuJoCo runtime/metrics and original surrogate/IK diagnostics
ml/               Teleop schemas, quarantine/review, dataset export, training/evaluation
integrations/     Synthetic hospital information, FHIR Task and RTLS contracts
shared/schemas/   Generated strict JSON contracts
data/             Evidence registry, pain points, 50 hospital seeds, quarantined image URLs
tests/            Core, API, safety, simulation, learning and evidence tests
scripts/          Setup, run, demo, contract export and acquisition tools
infra/            Container recipe (not validated in this environment)
docs/             Architecture, safety case, APIs, sources, research and known gaps
artifacts/        Actual demo/test/simulator outputs
assets/textures/  Nine reusable CC0 PBR maps; provenance in assets/provenance/
```

## Status and boundaries

- Persistent SQLite snapshots, task records and a hash-chained append-only API audit log.
- Clinical-first deterministic routing; model classification cannot downgrade a clinical trigger.
- Approval and simulation bound to a room snapshot and plan hash; stale state, E-stop and object prohibitions veto execution.
- Actual MuJoCo dynamics streamed to a detailed Three.js room, plus endpoint IK/contact diagnostics on synthetic robot geometry. Task validation checks semantic object paths and engine health; it does **not** validate a grasp or full robot trajectory. The planar base/wheel actuation is a surrogate rather than verified balancing or odometry.
- Synthetic teleoperation contracts and offline learning lifecycle with artifact hashes, held-out episodes, abstention and research-only promotion. Vendor VLA/Quest transport remains unconfigured.
- Optional Astra/Fable provider clients are disabled by default, accept synthetic input only, and were not tested against paid live APIs. Environment variables are documented in `.env.example`; the application does not automatically load that file.
- Research image corpus: **9 real URL metadata candidates, 1 hospital represented, 0 corpus image files, 0 training-approved images**. There are 50 distinct hospital seed targets; 1,000/50 coverage is not achieved. The **2 separately cached Stanford/UCLA photographs** are local architectural references only and do not increase that corpus count. The scene's **9 Poly Haven texture maps** are CC0 assets.

Read [KNOWN_GAPS](docs/KNOWN_GAPS.md), [TESTING](docs/TESTING.md), [HACKATHON_DEMO](docs/HACKATHON_DEMO.md), and [SOURCE_HIERARCHY](docs/SOURCE_HIERARCHY.md). This prototype makes no clinical approval, compliance, autonomous manipulation competence or measured staff-time-saving claim.
