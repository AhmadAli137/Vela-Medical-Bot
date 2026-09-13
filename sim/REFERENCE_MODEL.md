# Reference-informed Bracket Bot visual simulation

`reference_model.py` and `reference_runtime.py` form a second, separate simulator. The original `model.py` remains available for its existing regressions. This second model was built after inspecting the **original supplied handout image and extracted platform/teleoperation video frames**, rather than relying only on their written summaries.

The visible robot has a slender tall white mast/rack, transverse two-wheel base, independent shoulder stages, rounded white serial arms, wrist-camera housings and rotary grippers. The new body descriptors reproduce those proportions more closely. All dimensions, axes, masses, inertias, actuator gains and camera calibration remain inferred or synthetic. This is not vendor CAD or a validated digital twin.

`reference_body_descriptors.json` defines 27 robot bodies and one dynamic phone body with parent, local position, geometry, joint axis/range, link length/radius and initial world poses. The phone has its own GLB and is absent from the static room asset. Blender produces body-local visual meshes. A browser sets each top-level body's world position and quaternion directly from MuJoCo state; body names must match. Coordinates use +Z up, +X forward and +Y left. Quaternions are `[w,x,y,z]`; Three.js requires reordering into `[x,y,z,w]` and applying the scene's coordinate conversion consistently.

There are 25 actuated degrees of freedom: three constrained planar base joints, two wheel hinges, two independent lifts, fourteen arm joints and four gripper-finger hinges. A six-DOF free joint adds the phone's motion: the model has 32 position coordinates, 31 velocity coordinates and no equality constraints. Wheel angle targets follow commanded forward/yaw travel; the base remains a constrained planar surrogate. It does not simulate the real robot's balancing controller or validate wheel traction/odometry. Gravity compensation on the synthetic upper structure is an explicit simulator assumption; the phone has ordinary gravity and no gravity compensation.

```python
from sim.reference_runtime import ReferenceSimulation
simulation = ReferenceSimulation()
simulation.command("joint_demo")
state = simulation.state()
# state contains bodies, joints, mode, paused, simulation_time, metrics
simulation.command("reach_demo")
simulation.command("pause")  # toggle
simulation.command("reset")
simulation.command("pickup_demo")
# After metrics.pickup.success becomes true:
simulation.command("release_phone")
simulation.command("reset")
simulation.command("lift_demo")
```

`state()` advances real MuJoCo physics by elapsed wall time capped at 50 ms. `advance(seconds)` supports deterministic experiments, capped at two seconds per call. An internal lock serializes control and state access; no background motor-control thread or hardware endpoint exists.

`joint_demo` drives the synthetic actuators. `reach_demo` computes a left-arm endpoint IK solution plus a small base translation, samples 60 interpolated configurations for robot contacts, then tracks the joint targets with position servos. The green reach point is near the table edge. Actual post-step endpoint error is reported in `metrics.reach`; no object is attached and grasp success stays unknown. Position-only IK and finite sampled collision checking are not certified continuous-time collision avoidance.

Robot/self/environment contacts below the small numerical penetration tolerance stop the synthetic motion. During pickup/release, only the two left finger-to-phone contact pairs are allowed; phone-to-palm, arm-to-table and robot self contacts still stop. Ordinary phone-to-table/riser contacts are physical object support. This is a local numerical safeguard, not evidence of real E-stop/watchdog behavior. Hardware authorization remains false in both descriptors and every state/plan response.

## Physical phone pickup and vertical workspace

`pickup_demo` runs a fixed synthetic fixture: park the right arm, drive 0.78 m forward, solve a position-and-orientation IK hover, descend, close the left rotary fingers, lift and hold. The 82 × 158 × 12 mm, 180 g phone rests on a visible 35 mm riser on the table. The riser provides clearance beneath the thin phone for the gripper tips. Table dimensions are 0.80 × 0.80 m with a top surface at 0.7725 m.

The phone is moved only by MuJoCo gravity and contact forces. There is no weld, parenting, pose overwrite, kinematic attachment or gravity cancellation during pickup/release. Fingers have estimated rubber-like friction and bounded 0.22 Nm actuator torque; MuJoCo's no-slip solver refinement reduces artificial contact drift. These parameters are synthetic and tuned for this fixture, not measured from the reference robot.

The four approach stages receive 240 sampled collision checks. Loaded finger position targets intentionally lie beyond the object to maintain squeeze force; those commanded configurations are not treated as achievable kinematic states. Every executed step checks actual dynamics for unexpected contacts. Stage transitions preserve actuator control continuity so the gripper does not lose squeeze at the start of the lift/hold phases.

Success requires at least 0.15 m of measured phone elevation and simultaneous contact force from both fingers for two seconds. The checked native run lifted the phone approximately 0.228 m, held it for more than ten seconds, and then dropped it back onto the riser when `release_phone` opened the fingers. `metrics.pickup` reports current contact, forces, elevation, hold time, current success and whether a success previously occurred. A lost contact/height condition revokes current success. This is deterministic simulated manipulation of one known fixture; it is not a trained VLA result or evidence of hardware grasp reliability.

`lift_demo` first moves both arms clear of the base, lowers the two shoulder stages, raises them independently, reaches above head height, then folds and returns. Actual carriage travel is approximately 0.84 m. Measured end-effector heights span approximately 0.13–1.72 m; the head remains fixed at 1.67 m. The inferred carriage joint limits are −0.72 to +0.20 m. `metrics.lift` reports carriage travel and measured minimum/maximum hand heights. The mast/head do not telescope.

Both fixture demonstrations require the baseline scene. Starting from a displaced robot or phone rejects the command and requests an explicit reset; starting a task never silently teleports the phone. Other demos are blocked while a pickup is active. Release becomes available after a confirmed grasp, and pause/resume preserves the physics state.

Run tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_reference_sim.py tests/test_reference_pickup.py -q
.\.venv\Scripts\python.exe -m sim.reference_contact_report
```

## Public browser physics

The public static build uses `apps/web/src/browserPhysics.ts` and `browserPhysicsCore.ts`. It loads the same MJCF and descriptor files into **actual MuJoCo WebAssembly**, then performs Jacobian IK, sampled collision checks, actuator control and forward dynamics in the visitor's browser. The Three.js body transforms come from WASM `xpos`/`xquat`. No recorded pose stream or hosted Python process is needed for this demonstration.

The pinned `@mujoco/mujoco` 3.13.0 package is maintained by Google DeepMind. Its default single-threaded build requires no cross-origin isolation headers; the WASM file is bundled as a local Vite asset rather than loaded from a CDN. See the [official JavaScript bindings documentation](https://github.com/google-deepmind/mujoco/blob/main/wasm/README.md). The package's WASM payload is about 10.2 MB before transfer compression. Browser performance varies with the device.

The browser engine retains the same 50 ms elapsed-time cap, bounded public commands, collision stop and hardware prohibition as the Python reference runtime. Native and WASM pose IK endpoints agree within floating-point precision in the checked fixture. Browser physical pickup and release require their own actual WASM regression evidence; native evidence is not a substitute for that check.

From `apps/web`, run the actual WASM tests with:

```powershell
node --test --test-isolation=none tests/browser-physics-wasm.mjs
```

This uses Node's current in-process test mode to avoid Windows sandbox subprocess restrictions. The suite covers XML/body-pose parity, all 25 DOFs, runtime IK/native tracking parity, free-body pickup/hold/release, independent carriage travel, unreachable goals, collision stops, pause/reset/disposal and bounded elapsed-time stepping. Browser loader/network/render verification is performed separately on the static frontend. See [current results](../docs/TESTING.md).
