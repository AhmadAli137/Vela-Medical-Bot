# Camera views and patient assistance

Open the simulation and choose **More demos**:

| Task | Physical behavior | Completion checks |
| --- | --- | --- |
| Bring my phone | Grasp the free phone, carry it along the west side of the bed, lower it onto the patient's tray, open the fingers, and return home. | Bilateral grasp held while lifted, tray support before release, settled object, withdrawn hand, modeled reach distance, robot at rest. |
| Bring my meal | Carry a small sealed meal/snack container to a separate landing pad on the same tray. | The same contact, support, release, settling, and reach checks, measured for the meal body. |
| Open the blinds | Travel to the window, press a passive sliding handle, withdraw, and return home. | Actual hand contact force, at least 15 cm of handle travel, and all 16 slats rotated at least 1.10 radians. |

The earlier approach, greeting, phone-return, joint, reach, and vertical-travel demonstrations remain available. Each gallery start resets the scene. Pause preserves the current actuator targets; reset restores the initial objects, blinds, robot, and visual map.

The tray has a connected wheeled base, telescoping support and tabletop. Both pickup and delivery surfaces use 35 mm raised pads to give the rotary gripper room to open. The meal container measures 8.2 × 13 × 4 cm. These demonstrations deliver belongings and a container within an estimated reach envelope; they do not place objects into an articulated patient hand or feed the patient. The patient remains a static fictional adult model.

## Robot vision

**Robot vision → Camera views** displays synchronized head-left, head-right, left-wrist and right-wrist RGB views at 320 × 240 pixels. Click a camera caption to enlarge it. Head views use a modeled 54 mm stereo baseline and 90° vertical field of view; wrist views use 75°. MuJoCo supplies each optical pose, and Three.js renders the room and robot from that pose. These are simulated images, not a physical camera connection. The overview's cutaway front/right walls and ceiling are present in camera views so the cameras see an enclosed room.

**Visual map** displays landmarks and a camera trajectory estimated from stereo pixels. The custom feature-mapping implementation performs corner detection, binary-descriptor matching, stereo triangulation, robust pose estimation, keyframe insertion and map relocalization. Its API accepts only pixels, timestamps and calibration. It receives no simulator pose, depth buffer, object identity or room geometry. Simulator truth is calculated afterward in a separate evaluation record for accuracy checks; it is never used to repair or draw the estimated map. See [the visual localization implementation and limits](VISUAL_SLAM.md).

The optional **Pause motion if tracking is lost** control connects perception to motion. It requests an idempotent pause after 1.5 seconds without a valid fresh visual pose; frames older than 750 ms are stale. Camera streaming continues while physics is paused. Tracking recovery does not resume motion automatically; the user presses Resume. This is a simulation watchdog, not a certified safety system.

Assistance routes and grasp targets are planned from the known fixture. The visual map can gate motion, but it does not discover objects, plan paths, avoid newly observed obstacles or steer the base. The base uses bounded planar simulation joints, with no wheel traction or balancing model. This is a bounded visual SLAM prototype with scripted, contact-driven assistance, not autonomous room understanding or a learned VLA policy.

## Physics and verification

The model contains 27 robot bodies, 25 robot actuators, two free objects and 17 passive blind bodies: **46 synchronized body poses**. Sixteen joint equalities model the blind linkage; no equality attaches a phone or meal to the robot. Only robot actuators receive controls. Sampled route checks precede execution, and contact monitoring continues at every physics step. A missing grasp, lost carried-object contact, blocked route, unsupported release or failed measured outcome stops the demonstration.

The model, initial optical poses, visual assets and trajectory library share a revision contract. Changes to dimensions or dynamics require regeneration before either runtime accepts the library.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_reference_assistance.py
.\.venv\Scripts\python.exe -m sim.reference_glb_check
node --experimental-strip-types --test apps/web/tests/stereo-slam.mjs apps/web/tests/visual-tracking-guard.mjs
npm --prefix apps/web run build:public
node apps/web/scripts/check-assistance-vision.mjs
```

The Chrome checker observes visible controls and measured runtime outcomes. Set `VELA_GUARD_CHECK=1` to add a negative test that corrupts only camera pixel readback and verifies the motion pause, lack of automatic resume, and explicit resume. Set `VELA_PUBLIC_URL` to inspect a deployed site. `VELA_VISION_ONLY=1` skips task rollouts; `VELA_ASSISTANCE_COMMANDS` selects a comma-separated command list.

Reports: [native assistance rollouts](../sim/outputs/reference_assistance.json), [native test results](../artifacts/assistance-native-tests.xml), [WebAssembly checks](../artifacts/browser-contact-physics.json), [pixel estimator and guard tests](../artifacts/stereo-slam-tests.json), and [local Chrome observations](../artifacts/assistance-check.json). A report establishes only the checks it actually records. Favorable synthetic-image accuracy is separate from accuracy measured during motion in the hospital scene.
