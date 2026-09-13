# Actual validation results

## Three additional physics demos: September 13, 2026

The bedside approach, arm greeting and controlled phone return have passing results for **29 native/API checks** and **19 actual MuJoCo WebAssembly tests**. The WASM suite finished in 27.861 seconds and includes the prior pickup, release and vertical-travel regressions. Fault tests cover lost phone contact, missing support, invalid trajectories, completion revocation and reset requirements. The native summary records the initial test-assertion correction and Windows temporary-directory setup errors alongside the passing rechecks. [Native/API results](../artifacts/more-demos-native-summary.json), [native measured rollouts](../sim/outputs/reference_more_demos.json), [WASM measurements](../artifacts/browser-contact-physics.json).

All three passed the production-build Chrome check in **85.602 seconds**, including measured outcomes, pause/resume, switching, reset and gallery keyboard behavior. No browser errors, failed requests or API calls occurred. The gallery was also checked at 390 × 844 pixels: all three start controls were reachable without horizontal overflow, and Escape restored focus. [Chrome report](../artifacts/more-demos-check.json), [demo menu](../apps/web/artifacts/more-demos-gallery.png), [mobile menu](../apps/web/artifacts/more-demos-mobile-menu.png). See [demo behavior and limits](MORE_DEMOS.md).

The same three-demo check passed on **live Vercel** in **84.465 seconds**, with zero browser, HTTP, network or API errors. The deployed phone return included a confirmed 22.8 cm lift, measured support before release, and a settled return within 1.257 mm horizontally of its target. [Production results](../artifacts/vercel-more-demos-check.json), [live phone hold](../apps/web/artifacts/vercel-more-demos-phone_return_demo-action.png).

## Furnished patient room: September 13, 2026

The evaluated Blender mesh audit passes **195 furniture and support parts** across all seven furniture assemblies. Required casters, legs, rail sockets and bars, handle mounts, cabinet bases, cup and planter parts are present. All included parts have surface-connected paths to the floor; pillow and patient blanket support checks also pass. The audit distinguishes cloth spanning between legs from direct support over the body. [Mesh/contact audit](../artifacts/room-visual-audit.json), [bedding regression fixtures](../artifacts/bedding-audit-regressions.json), [missing/displaced-part regressions](../artifacts/room-audit-regressions.json).

The updated furniture and fixed patient collision shapes passed **15 native MuJoCo tests** in 17.62 seconds and **11 WebAssembly tests** in 13.001 seconds, including the existing phone pickup and vertical travel. Deliberately placing the robot into the patient's occupied space triggers the simulator contact stop. [Native JUnit result](../artifacts/patient-room-physics-tests.xml), [current WASM measurements](../artifacts/browser-contact-physics.json). The patient is a static fictional adult visual model; these checks do not simulate physiology or validate contact with a real person.

See [scene construction and source assets](PATIENT_ROOM.md).

The final static build passed the nine-view Chrome check in **31.631 seconds**, with eight loaded room assemblies and no JavaScript errors, failed requests or local API calls. Visual review confirmed continuous chair upholstery, connected bed supports and corrected patient eye transparency. The planter comparison uses containment within conservative source bounds for rotated leaves; the other assemblies use bounds agreement. [Browser report](../artifacts/room-completeness-check.json), [chair close-up](../apps/web/artifacts/room-chair.png), [patient view](../apps/web/artifacts/room-patient.png).

The furnished patient room also passed the same nine-view check on **live Vercel** in **34.09 seconds**, with zero browser errors, failed requests or API calls. Its scene revision `e910282b948201f7` matches the committed asset bytes; Windows source line endings account for the different local build revision. [Production report](../artifacts/vercel-room-completeness-check.json), [live patient view](../apps/web/artifacts/vercel-room-patient.png), [live chair view](../apps/web/artifacts/vercel-room-chair.png).

## Corrected geometry and physical manipulation

The revised model passed **20 focused tests** (14 native physics and 6 API) in 17.46 seconds, with one dependency deprecation warning. The phone is a 0.18 kg free body: it rises 22.8 cm, sustains contact with both fingers, and drops under gravity after release. There are no equality constraints or runtime object-pose writes in the pickup. Independent shoulder stages travel 84 cm; the end-effector sites span 13.2–172.4 cm above the floor with no unexpected robot contacts in the tested 26-second sequence. Release clears current grasp success immediately; a collision fault invalidates success and requires reset. [Final focused JUnit result](../artifacts/reference-corrections-test-results.xml), [contact and lift measurements](../sim/outputs/reference_contact_manipulation.json).

The pickup uses a visible 35 mm raised rest and tuned synthetic contact parameters. This evidence covers one fixed fixture; it does not establish pickup from a flat table, robustness to other objects, wheel-driven balance or calibrated hardware dynamics.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_reference_sim.py tests/test_reference_pickup.py tests/test_reference_api.py --basetemp=.cache/reference-check
.\.venv\Scripts\python.exe -m sim.reference_contact_report
.\.venv\Scripts\python.exe -m sim.reference_glb_check
```

The GLB audit validates **28 body poses**: 27 robot bodies and the separate dynamic phone. All four textured room primitives have finite, bounded UV accessors and matching vertex counts; the static room contains no phone mesh. Seven deliberately malformed assets were rejected. [Pose/UV report](../sim/outputs/reference_glb_check.json), [negative-case audit](../artifacts/reference-glb-audit-regressions.json). This verifies the coordinate and asset contracts, not vendor geometry.

## Browser verification

The corrected **live Vercel deployment passed anonymous Chrome verification** on September 13, 2026 in **70.601 seconds**. All 25 joints moved, 28 bodies synchronized, hand heights reached 0.1325–1.7239 m, and the phone rose 22.84 cm with bilateral contact before falling on release. There were zero browser errors, failed requests or local API calls. [Production report](../artifacts/vercel-browser-check.json), [live pickup screenshot](../apps/web/artifacts/vercel-pickup.png).

The earlier **11-test MuJoCo WebAssembly suite passed** in 13.001 seconds with the furnished patient room; the expanded 19-test suite is recorded above. The browser controller lifts the phone 22.7889 cm, sustains bilateral contact for 15.918 seconds in the measured run, and releases it under gravity. It also passes the forced collision-stop regression and native pose/reach parity checks. [WASM contact measurements](../artifacts/browser-contact-physics.json).

The full Chrome check on the static build passed in **72.646 seconds**, with zero browser errors, failed requests or local API calls. It exercised all 25 joints, pause, reach, low/high travel, pickup, sustained hold and gravity release. All five scene requests used the same asset revision. [Browser report](../artifacts/public-browser-check.json), [pickup screenshot](../apps/web/artifacts/public-pickup.png), [recorded demonstration](../apps/web/artifacts/contact-pickup-demo.mp4).

```powershell
npm --prefix apps/web run build:public
$env:VELA_PUBLIC_URL = 'https://vela-medical-bot.vercel.app'
node apps/web/scripts/check-public-demo.mjs
```

The corrected renderer has been inspected in actual Chrome: the floor artifacts are gone, furniture connections are visible and 28 bodies synchronize without independent link interpolation. [Browser image](../apps/web/artifacts/render-revision-simulation.png), [render check](../artifacts/render-revision-browser-check.json). The separate [Blender Cycles preview](../assets/simulation/reference-room-preview.png) is an offline render, not a browser screenshot.

The original production browser check, before this correction, passed in 24.42 seconds with 27 bodies and a reach demonstration. That older build did **not** grasp a phone. The old [recording](../apps/web/artifacts/immersive-motion.mp4) is historical evidence for that earlier model. The [joint/reach report](../sim/outputs/reference_actuation.json) has been regenerated for the corrected model; contact pickup has its own report above.

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
