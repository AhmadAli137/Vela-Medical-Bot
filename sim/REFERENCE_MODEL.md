# Reference-informed Bracket Bot visual simulation

`reference_model.py` and `reference_runtime.py` form a second, separate simulator. The original `model.py` remains available for its existing regressions. This second model was built after inspecting the **original supplied handout image and extracted platform/teleoperation video frames**, rather than relying only on their written summaries.

The visible robot has a slender tall white mast/rack, transverse two-wheel base, independent shoulder stages, rounded white serial arms, wrist-camera housings and rotary grippers. The new body descriptors reproduce those proportions more closely. All dimensions, axes, masses, inertias, actuator gains and camera calibration remain inferred or synthetic. This is not vendor CAD or a validated digital twin.

`reference_body_descriptors.json` defines 27 named bodies with parent, local position, geometry, joint axis/range, link length/radius and initial world poses. Blender can produce detailed body-local visual meshes. A browser sets each top-level body's world position and quaternion directly from MuJoCo state; body names must match. Coordinates use +Z up, +X forward and +Y left. Quaternions are `[w,x,y,z]`; Three.js requires reordering into `[x,y,z,w]` and applying the scene's coordinate conversion consistently.

There are 25 actuated degrees of freedom: three constrained planar base joints, two separate wheel hinges, two independent lifts, fourteen arm joints and four gripper-finger hinges. The base is a constrained planar surrogate and the wheel hinges are separately actuated. It does not simulate the real robot's balancing controller or validate wheel odometry. Gravity compensation on the synthetic upper structure is also an explicit simulator assumption.

```python
from sim.reference_runtime import ReferenceSimulation
simulation = ReferenceSimulation()
simulation.command("joint_demo")
state = simulation.state()
# state contains bodies, joints, mode, paused, simulation_time, metrics
simulation.command("reach_demo")
simulation.command("pause")  # toggle
simulation.command("reset")
```

`state()` advances real MuJoCo physics by elapsed wall time capped at 50 ms. `advance(seconds)` supports deterministic experiments, capped at two seconds per call. An internal lock serializes control and state access; no background motor-control thread or hardware endpoint exists.

`joint_demo` drives the synthetic actuators. `reach_demo` computes a left-arm endpoint IK solution plus a small base translation, samples 60 interpolated configurations for robot contacts, then tracks the joint targets with position servos. The green reach point is near the table edge. Actual post-step endpoint error is reported in `metrics.reach`; no object is attached and grasp success stays unknown. Position-only IK and finite sampled collision checking are not certified continuous-time collision avoidance.

Robot/self/environment contacts below the small numerical penetration tolerance stop the synthetic motion. This is a local numerical safeguard, not evidence of real E-stop/watchdog behavior. Hardware authorization remains false in both the descriptors and every state/plan response.

Run tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_reference_sim.py -q
```

## Public browser physics

The public static build uses `apps/web/src/browserPhysics.ts` and `browserPhysicsCore.ts`. It loads the same MJCF and descriptor files into **actual MuJoCo WebAssembly**, then performs Jacobian IK, sampled collision checks, actuator control and forward dynamics in the visitor's browser. The Three.js body transforms come from WASM `xpos`/`xquat`. No recorded pose stream or hosted Python process is needed for this demonstration.

The pinned `@mujoco/mujoco` 3.13.0 package is maintained by Google DeepMind. Its default single-threaded build requires no cross-origin isolation headers; the WASM file is bundled as a local Vite asset rather than loaded from a CDN. See the [official JavaScript bindings documentation](https://github.com/google-deepmind/mujoco/blob/main/wasm/README.md). The package's WASM payload is about 10.2 MB before transfer compression. Browser performance varies with the device.

The browser engine retains the same 50 ms elapsed-time cap, bounded public commands, collision stop, unknown grasp result and hardware prohibition as the Python reference runtime. Native and WASM reach endpoints agree within floating-point precision in the regression suite. The checked run reached the synthetic endpoint with 0.000317791668951 m error after 3,000 physics steps; this remains a point-reaching experiment, not object manipulation competence.

From `apps/web`, run the actual WASM tests with:

```powershell
node --test --test-isolation=none tests/browser-physics-wasm.mjs
```

This uses Node's current in-process test mode to avoid Windows sandbox subprocess restrictions. Seven tests cover XML/body-pose parity, all 25 DOFs, a 16-second contact-free cycle, runtime IK/native tracking parity, unreachable goals, actual contact stop, pause/reset/disposal and bounded elapsed-time stepping. Browser loader/network/render verification is performed separately on the static frontend.
