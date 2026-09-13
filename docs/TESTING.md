# Actual validation results

## Live Vercel browser validation

Anonymous Chrome verification passed at **https://vela-medical-bot.vercel.app** in 24.42 seconds. All 25 joint values changed; 27 body meshes stayed synchronized; pause held simulation time stable; the reach settled with a displayed 0.1 cm endpoint error. There were zero browser errors, failed network requests, or calls to the local `/api` backend. Default routing, legacy hash isolation, and About-dialog Escape/focus restoration also passed. [Measured production result](../artifacts/vercel-browser-check.json), [production screenshot](../apps/web/artifacts/vercel-simulation.png).

The equivalent standalone static-server test passed before deployment. Seven additional actual WebAssembly engine tests passed, including native/WASM pose and reach parity, all actuator DOFs, unreachable goals, contact stopping, pause/reset/disposal, and the bounded catch-up interval. Public and normal TypeScript/Vite production builds both passed.

```powershell
$env:VELA_PUBLIC_URL = 'https://vela-medical-bot.vercel.app'
node apps/web/scripts/check-public-demo.mjs
```

## Reference-based interactive room: September 12, 2026

The rebuilt view at `http://127.0.0.1:8000/#simulation` passed a focused final run of **14 tests** (9 physics and 5 API tests), in 7.44 seconds with the same dependency deprecation warning. [JUnit evidence](../artifacts/reference-test-results.xml).

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_reference_sim.py tests/test_reference_api.py --basetemp=.cache/reference-final-local
.\.venv\Scripts\python.exe -m sim.reference_glb_check
```

The final Blender-exported robot GLB contains 114 nodes, including all **27 expected physics bodies**, whose exported transforms match the MuJoCo initial world poses. [Transform check](../sim/outputs/reference_glb_check.json). This verifies the visual/physics coordinate contract, not calibrated hardware geometry.

The final Chrome session loaded both GLBs and recorded joint motion followed by a reach, with no reported JavaScript exceptions or console errors. Its two sampled joint states differed on 24 of 25 coordinates; the separate deterministic motion test exercises all 25 over a full cycle. The recorded reach had zero reported contacts and approximately 0.55 mm synthetic endpoint error. No object attachment or grasp was simulated. The original full-cycle physics report is [reference_actuation.json](../sim/outputs/reference_actuation.json).

View the [recorded MP4](../apps/web/artifacts/immersive-motion.mp4), [bedside screenshot](../apps/web/artifacts/immersive-final-bedside.png), and [joint-motion screenshot](../apps/web/artifacts/immersive-final-joints.png). The browser renders a detailed authored scene; the separate [Blender Cycles preview](../assets/simulation/reference-room-preview.png) uses offline lighting and is not a browser screenshot. Final TypeScript/Vite build passed. The one-click launcher was checked against the existing local server; its cold-start branch was not separately exercised.

Validation used Python 3.12.10, MuJoCo 3.13.0, Node 24.14.1 and local Chrome. Exact installed Python packages are in `requirements.lock`; frontend dependencies are locked in `apps/web/package-lock.json`. No test result from the supplied old status file was reused.

## Python suite

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.cache/all-tests-01 --junitxml=artifacts/pytest-results.xml
```

Result: **148 passed, one dependency deprecation warning, 6.92 seconds**. The warning is Starlette's reference to `anyio.abc.BlockingPortal`; it did not fail the suite. See [JUnit report](../artifacts/pytest-results.xml).

Coverage includes clinical/mixed request priority, schema rejection, world diffs, desired-state readiness, object authority, stale approval/simulation, E-stop, exclusive takeover, cancellation preservation, operator ownership, role boundaries, cloud failure fallback, audit transaction rollback, real MuJoCo dynamics/IK/contact regression, abstention scenarios, synchronized teleop frames, consent/review/export, actual tiny-policy training and held-out evaluation, artifact integrity, promotion/rollback, research scores, rights and crawler constraints.

Initial sandbox runs failed because pytest's mode-700 temporary directories were inaccessible under this Windows managed sandbox. Retrying the same checks with sandbox elevation resolved the filesystem failure. An early collection error from using pytest's reserved `request` parameter was fixed before the passing run. These failures were not successful tests.

## Integrated demo

```powershell
.\.venv\Scripts\python.exe -m scripts.run_demo
```

Result: **three workflows passed**, clinical route D, valid audit chain, **zero real robot actions**. [Recorded output](../artifacts/demo-report.json) contains the actual plan, simulation scope, safety trace and verification for each workflow. The correction episode contains 12 synthetic frames and remains quarantined.

## Simulator and learning

```powershell
.\.venv\Scripts\python.exe -m sim benchmark --episodes 12 --seed 7 --output sim/outputs
.\.venv\Scripts\python.exe -m sim render --output sim/outputs --camera overview
.\.venv\Scripts\python.exe -m ml demo --output ml/outputs
```

The recorded simulator suite ran **12 episodes / 3,600 physics steps**, with finite dynamics in all episodes and zero episodes with robot contacts in this fixture. Endpoint IK and deterministic abstention are scored. Physical grasp, bimanual manipulation and hospital task success are **not measured**. Head and both wrist camera renders are also checked in.

The learning demonstration generated **five synthetic episodes / 60 frames**, fit a ridge behavior-cloning policy on **48 frames**, and evaluated **12 held-out frames** from a different episode. The recorded action RMSE is approximately **9.65e-8 m** on synthetic linear labels. This deliberately simple regression has no image pixels or language training, and is not a VLA competency result. Policy activation awaits explicit research signoff.

## Frontend

```powershell
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e
```

The TypeScript/Vite production build passes. Four actual Chrome browser tests passed against the running API/Vite application: task lifecycle and phone verification, clinical routing/privacy, all four views plus a measured MuJoCo benchmark, and 390-pixel mobile layout with keyboard dialog focus/Escape restoration. Screenshots are saved in `apps/web/artifacts/`. Run the API on 8000 and Vite on 5173 before browser tests; local Chrome is required by the test configuration. Vite/Chrome process spawning required sandbox elevation here.

## Not validated

No robot, Quest device, real patient, clinical pilot, live hospital integration, paid Astra/Fable call, hardware VLA, infection-control process, regulatory certification, container build or Linux deployment was tested. No production workload, penetration test, full WCAG audit or validated clinical triage accuracy is claimed.
