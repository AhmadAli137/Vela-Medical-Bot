# MuJoCo simulation: what runs and what it proves

Current entrypoints and synchronization are described in the [app guide](APP_GUIDE.md). The native viewer now uses the reference scene and shared local session when opened from the app; the original primitive model remains an explicitly labeled benchmark.

The repository loads and steps a real MuJoCo MJCF model. It is an explicitly **unverified synthetic robot**, with topology motivated by the supplied Bracket Bot summaries. No CAD, URDF, vendor inertias, calibrated camera transforms or production control limits were supplied. Every numeric link size, axis orientation, mass, joint range, gain, force bound and camera calibration is a synthetic test fixture, not a Bracket Bot specification.

The current model contains two wheel velocity motors, independent shoulder lifts, two seven-joint serial arms, rotary grippers, stereo head and wrist cameras. There are 22 physical actuators. Wheel-ground contact produces translation and yaw; there are no base X/Y/yaw driving actuators. Passive guides preserve an upright chassis and allow a small vertical displacement to load the tires. Upper-body gravity compensation and estimated dynamics remain research approximations. This is not active two-wheel balancing or verified hardware dynamics.

The current reference room contains the complete visual furniture, a static clothed patient, a free phone and meal container, and a passive blind mechanism. Simplified collision geometry drives contact; visual meshes add no mass or collision. The robot has independent shoulder lifts and a fixed mast/head. See [assistance and camera results](ASSISTANCE_AND_VISION.md).

## Run

From the repository root after dependency installation:

```powershell
.\.venv\Scripts\python.exe -m sim viewer
.\.venv\Scripts\python.exe -m sim generate --output sim/scenes/mock_room --seed 7
.\.venv\Scripts\python.exe -m sim benchmark --episodes 12 --seed 7 --output sim/outputs
.\.venv\Scripts\python.exe -m sim render --camera overview --output sim/outputs
.\.venv\Scripts\python.exe -m sim render --camera head_rgb --output sim/outputs
.\.venv\Scripts\python.exe -m sim render --camera left_wrist --output sim/outputs
.\.venv\Scripts\python.exe -m sim render --camera right_wrist --output sim/outputs
```

`viewer` opens the current detailed scene in a standalone native window. Use `--connect http://127.0.0.1:8000` to display the same running session as the local browser; the app and command-file launcher select this shared mode automatically. Drag to orbit, scroll to zoom, Space to pause, R to reset, C to cycle cameras, and V to inspect collision shapes. The overlay lists number keys for the same manipulation and movement demos as the browser.

`render` renders the current reference scene. `generate` exports a self-contained native model. Graphics-driver availability is required for rendering; physics stepping does not depend on a browser or renderer. Legacy `render` and `generate` remain available with `--legacy`.

## Legacy benchmark and mock workflow validation

The following diagnostics retain the **older primitive surrogate**, not the current patient-room demonstration. Its proxies include wheelchair, cart, sliding drawer, hinged door, rigid bag and randomized clutter. Retaining the fixture preserves historical benchmark comparisons.

`sim.engine.run_benchmark(episodes, seed)` commands both shoulder yaw joints and the vertical stage, executes 300 physics steps per episode, measures finite state, self/environment contacts, lift displacement and maximum generalized speed, then tests position-only damped IK near the left wrist. Mass, friction, clutter and table geometry vary with seed. The report records actual contact counts rather than removing unexpected contacts from the score. IK is an endpoint calculation, not collision-free motion planning.

The benchmark also evaluates a **deterministic** abstention envelope on permitted/prohibited objects, identity uncertainty, excessive load, nearby person, attached object, policy OOD, poor grasp and blocked path. Those fixture labels are not learned VLA performance. Person entry is tested as a current perception/clearance input, not a physically simulated moving human.

`replay_trajectory(frames, robot_revision="surrogate_v1")` replays bounded synthetic arm/lift position targets using real MuJoCo servo dynamics. It stops on detected robot contacts/nonfinite dynamics, enforces monotonic samples and a maximum 100 ms gap, and rejects vendor recordings without a verified joint mapping. It does not replay image pixels, base trajectories, gripper trajectories or a real Quest stream.

`validate_plan(plan, room)` is a deliberately narrower application diagnostic: sampled swept-object paths versus room/person/protected zones, plus MuJoCo load/step smoke validation. It does **not** simulate the application's complete room geometry, robot trajectory or grasp. Results explicitly contain:

```json
{
  "hardware_model_verified": false,
  "authorizes_hardware": false,
  "metrics": {"trajectory_validated": false, "grasp_validated": false}
}
```

The application may use this diagnostic for its software world-state demo only. Hardware authorization remains blocked by the independent safety service.

## Legacy benchmark results

`sim/outputs/evaluation.json` is generated by the command above, and contains the seed, model hash, MuJoCo version, per-episode records and limitations. Task success, grasp success, bimanual manipulation success and sim-to-real gap remain JSON null in this older benchmark; the current reference demo has separate measured contact-manipulation reports. The simulator tests additionally force a robot/furniture overlap to prove contacts are detected, exercise unreachable IK, and check a person entering a candidate object path.

## Replacing the surrogate

Replacement requires verified CAD/kinematics and inertias, collision pairs, actuator and payload-dependent limits, real gripper geometry, joint/control API mapping, stereo/wrist calibration and synchronization, vendor stop/watchdog primitives, plus measured lab trajectories. Validate model hashes, range/mass/inertia consistency, camera frames and real-versus-sim error before changing any verification flag. A model flag alone cannot grant hospital operational approval.

Implementation uses the official [MuJoCo Python API](https://mujoco.readthedocs.io/en/stable/python.html) for XML loading, named access, Jacobians, stepping and rendering. This reference was checked during implementation; the recorded runtime reports the installed version.
