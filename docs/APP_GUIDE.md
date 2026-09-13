# Which Vela app should I use?

Start with **Simulation studio** to watch the robot, camera views and assistance demonstrations. Vela is one repository with several interfaces; the four workflow screens are tabs in the same local web application.

| Interface | How to open it | What it does |
| --- | --- | --- |
| Public simulation | [vela-medical-bot.vercel.app](https://vela-medical-bot.vercel.app) | Detailed room and real MuJoCo physics running inside your browser. Each tab has its own session. |
| Local simulation | `Open Simulation.cmd`, or `http://127.0.0.1:8000/#simulation` | The same scene and demo definitions, with Python MuJoCo running on your computer. Includes the simulated cameras and experimental stereo mapping. |
| Native MuJoCo window | `Open Native Simulation.cmd`, or **App guide → Open native MuJoCo** in the local app | MuJoCo's desktop renderer displays the same visual assets and follows the local server's current physics state. Keyboard and browser controls act on that shared session. |
| Room operations | `Open Workspace.cmd`, or `http://127.0.0.1:8000/#staff` | Mock room snapshots, requests, task review, approvals and result records. |
| Patient experience | `http://127.0.0.1:8000/#patient` | Practice patient requests and routing. No hospital staff are contacted. |
| Robot & fleet | `http://127.0.0.1:8000/#fleet` | Mock robot status, permissions, correction sessions and skill records. Hardware camera placeholders refer to unconnected hardware; simulated camera images are in Simulation studio. |
| Research studio | `http://127.0.0.1:8000/#research` | Evidence, the explicit legacy benchmark, image corpus and offline learning workflow. |

The local server must be running for the localhost links. The command files start it if needed. **App guide** is available in the simulation header and workspace sidebar, with links between the views.

Native controls: **Space** pauses, **R** resets, **C** cycles robot cameras, **O** restores the room view, **V** switches detailed/collision geometry, and **H** shows all demo keys. Keys **8 / 9 / 0** reset and run phone delivery / meal delivery / blinds.

## What is synchronized?

The local and public simulations use the same reference physics XML, body descriptors, trajectories and four GLB assets: room, robot, phone and meal container. The native renderer imports those GLBs rather than reconstructing another room. Its additional display meshes have no collision or mass contribution; the existing contact shapes and body inertias remain authoritative.

A native window opened through the local app attaches to its backend. The backend supplies one coherent set of joint positions, velocities, actuator controls, object poses and simulation time. The native window uses forward kinematics to display that state; it does not advance a second physics clock. Pause, reset and demo commands go back to the same server.

The Vercel website runs physics on each visitor's own device. It does **not** broadcast state to your local computer or other tabs. Running `python -m sim viewer` directly also creates a separate standalone session; use `--connect http://127.0.0.1:8000` to attach it to the local app.

## What makes the robot move?

MuJoCo is the physics engine, but the robot's behavior depends on the model supplied to it. The earlier model used independent base translation/turning servos with decorative wheel rotation, which allowed unrealistic sideways travel. The corrected model removes those base drive servos. Two wheel motors now push against the floor through contact and friction, and the route controller turns before driving along a new direction.

The chassis is still held upright by passive simulation guides, with small vertical movement to load the tires. This models wheel propulsion without claiming that active balancing or vendor dynamics have been validated. Look under **Model & physics** for measured wheel-drive information.

## Why can the pictures still differ?

Three.js and native MuJoCo have different lighting and material renderers. The room layout, patient, robot parts and their poses come from the same assets and model, but their pixels are not identical. Native collision inspection deliberately displays simplified contact geometry. Switch back to the detailed view to see the furniture and robot meshes.

## What is still separate?

The workflow screens use a synthetic task database and a schematic room diagram. Approving a workflow task changes that mock state; it does **not yet dispatch the corresponding physical manipulation in the 3D simulator**. A completed workflow task therefore is not evidence of a successful grasp. Use Simulation studio's measured demo results for physical simulation outcomes.

Research studio retains the older randomized primitive room solely as an explicitly labeled benchmark so historical results remain comparable. `python -m sim benchmark` still runs that benchmark. Default `viewer`, `render` and `generate` commands now use the current reference scene; legacy render/generate require an explicit option.

The learned baseline is an offline synthetic state-feature model. Camera mapping is an experimental stereo SLAM implementation with measured drift and tracking losses; assistance demos follow planned routes. Neither is a deployed robot autonomy system. See [assistance and vision](ASSISTANCE_AND_VISION.md) for the measured capabilities and limits.
