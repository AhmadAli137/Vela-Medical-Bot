# New Bracket Bot integration contract

**Evidence basis:** user-provided Hack the North 2026 Bracket Bot handout plus the three supplied demonstration videos. Public/legacy Bracket Bot sources remain useful only where explicitly noted.

## 1. Confirmed new-platform capabilities

The handout materially reduces the number of unknowns in the earlier specification. The application can now treat the following as **confirmed platform-level capabilities for planning purposes**:

| Capability | Confirmed detail | Application implication |
|---|---|---|
| Head perception | Custom stereo depth camera, stated 180° view, 2560×960 video | Wide room perception, RGB/depth world-state updates, navigation support |
| Wrist perception | Camera on each arm, stated for visual servoing | Close-range grasp refinement, occlusion recovery, bimanual manipulation feedback |
| Arms | Dual 7-DOF arms | Bimanual manipulation rather than single-arm pick-and-place only |
| Vertical workspace | Independent shoulder vertical linear stage | Manipulation across low floor-level and high bedside/shelf workspaces |
| Reach | Stated floor-to-6-ft height | Broad room interaction envelope; exact geometric reach still needs vendor CAD/model |
| Payload | 2 kg per arm | Many non-clinical personal items, lightweight room objects, clean supplies; policy and grasp stability still govern |
| Grippers | Rotary pincher; 50 kg·cm stall-servo claim | General grasping potential, but exact force/geometry must be runtime/vendor verified |
| Audio | Speaker + microphone; speaker advertises AEC | Voice-first patient/staff interface and conversational teleoperation support |
| Onboard compute | Jetson Orin Nano Super 8 GB | Edge perception/control and local preprocessing; do not assume all foundation-model inference is local |
| Drive | Hub BLDC motors, stated 8.5 N·m | Mobile manipulation and hospital-room navigation |
| Mapping/navigation | SLAM + localization + autonomous movement out of the box; handout states ~5 min to first map navigation | Use vendor navigation stack as the default base layer rather than rebuilding SLAM for the MVP |
| Teleoperation | Custom IK + Meta Quest controllers | Fast human demonstrations, recovery, supervised task execution, VLA dataset collection |
| VLA workflow | `TELEOPERATE > COLLECT DATA > TRAIN > DEPLOY` | Learned manipulation is a first-class platform path, not an optional afterthought |
| Shared training | 8× NVIDIA H100 node stated for policy training | Enables hackathon-scale VLA fine-tuning/experiments if access is actually provisioned |

These facts **do not** provide exact link meshes, joint limits, control rates, camera calibration, gripper geometry, drive dimensions, watchdog behavior, or the production SDK API. Those remain execution blockers until obtained from the robot/runtime.

## 2. What the supplied demos add

### 2.1 Onboard multi-camera views
The supplied camera demo shows simultaneous head and both arm/wrist perspectives. This validates a perception architecture that can fuse:

- wide head/stereo context;
- left wrist close-up vision;
- right wrist close-up vision;
- robot proprioception.

For manipulation, this is substantially better than a head-camera-only architecture because the wrist views remain useful when the target is occluded by the arm, gripper, bedside furniture, or another object.

### 2.2 Platform demo
The platform demo visibly pairs robot motion in a cluttered indoor environment with a live 3D map/point-cloud-style visualization. Together with the handout's explicit SLAM/navigation claim, the hospital app should treat localization and navigation as a vendor platform service and focus custom work on room semantics, task planning, patient/staff workflows, and manipulation.

### 2.3 Meta Quest teleoperation demo
The teleoperation demo shows **coordinated two-arm handling of a flexible black fabric item**: lifting, reorienting, spreading, and repositioning it over a table. This is much more consequential than a rigid-block pick-and-place demo. It demonstrates that the hardware can produce bimanual trajectories for deformable-object tasks under human control.

It does **not** establish autonomous performance. It establishes a valuable data-collection mechanism: a skilled operator can create synchronized demonstrations from the robot's actual cameras, joints, grippers, linear stage, and base for subsequent VLA training.

## 3. Application architecture: deterministic skills + VLA skills

The hospital application should use a **hybrid skill router** rather than force every task through either classical robotics or an end-to-end VLA.

### Deterministic / classical path
Best for:

- point-to-point navigation;
- room scans and state diffs;
- known rigid-object poses;
- predefined room-state transformations;
- fixed safe grasps;
- clearance-critical motion;
- any task where repeatability matters more than generalization.

Path:

`goal -> semantic planner -> motion planner / IK -> MuJoCo validation -> safety kernel -> Bracket Bot SDK`

### VLA path
Best for bounded tasks where perception and manipulation cannot be reliably reduced to a fixed pose script, such as:

- retrieving an approved personal object from clutter;
- bimanual handling of deformable clean linens or bags in a controlled room;
- opening/positioning approved non-clinical objects with variable geometry;
- novel-but-allowlisted object manipulation;
- visually closed-loop grasp refinement using wrist cameras;
- learned room-reset subtasks that vary too much for hard-coded waypoints.

Path:

`goal -> policy router -> approved VLA policy -> action proposal/short horizon rollout -> deterministic safety envelope -> robot SDK -> re-observe`

**A VLA expands capability; it does not expand authority.** The exact same hospital policy, no-go object classes, person-clearance rules, E-stop/watchdog, action limits, and post-action verification remain in force.

## 4. VLA data contract

A teleoperated demonstration episode should capture, on a common clock:

- task instruction / goal text;
- room and object IDs from the semantic world model;
- head stereo RGB/depth stream;
- left wrist-camera stream;
- right wrist-camera stream;
- base pose/velocity and localization quality;
- linear-stage position/velocity;
- left/right arm joint positions, velocities and (if exposed) effort;
- left/right gripper state;
- operator command/action representation from Meta Quest;
- safety events / collisions / protective stops;
- task completion label;
- failure reason and human corrections;
- policy/version/model hash when replayed autonomously.

The training corpus must be collected in mock rooms or approved research environments, not by casually harvesting patient-room video. PHI and patient imagery are excluded by default.

## 5. Mandatory startup handshake

Before live autonomous manipulation, the adapter must obtain or be provisioned with:

1. platform/firmware/SDK versions;
2. immutable robot/kinematic model hash;
3. exact base kinematics and dimensions;
4. exact linear-stage travel/limits;
5. both arms' joint names, axes, limits and control modes;
6. velocity, acceleration and effort limits;
7. collision geometry and self-collision configuration;
8. gripper geometry, limits, sensed state and grasp semantics;
9. exact payload/reach envelope and payload-dependent limits;
10. head/wrist camera intrinsics/extrinsics and timestamp synchronization;
11. state-feedback rates and command rates;
12. hardware emergency-stop state;
13. independent watchdog/command timeout behavior;
14. vendor-supported stop/hold/recovery primitives;
15. fault-state/protective-stop semantics;
16. VLA policy interface, action representation and maximum command horizon if vendor-provided.

If any item required by the requested action is unknown, the application falls back to observe, ask, teleoperate, or route to staff.

## 6. Application-level primitives

The hospital application should consume stable high-level primitives rather than raw motor calls. Proposed abstraction:

- `observe()` -> synchronized head/wrist sensor frames + robot state
- `navigate(goal, constraints)`
- `look_at(target)`
- `speak(text)` / audio session
- `linear_stage(target_height)` when verified
- `get_arm_state(arm)`
- `solve_ik(arm, target_pose, constraints)` when vendor-exposed
- `execute_trajectory(verified_trajectory_id)`
- `gripper/open` / `gripper/close` when verified
- `teleop/start` / `teleop/stop` / `teleop/record_episode`
- `vla/execute(policy_id, task_id, bounded_constraints)` only through the safety supervisor
- `stop()` / `hold()`
- `capabilities()`

Astra and Fable never bind directly to these robot primitives. A deterministic execution/safety service owns them.

## 7. New-to-simulator model replacement

The existing placeholder MJCF must be replaced with a model that represents the actual new robot:

- differential/mobile base and collision footprint;
- vertical shoulder linear stage;
- **two** 7-DOF arms;
- two rotary pincher grippers;
- head stereo/depth camera frame;
- left and right wrist-camera frames;
- inertias/payload limits;
- self-collision geometry.

The replacement process must record source/version, model hash, conversion steps, joint-range tests, mass/inertia checks, collision regression tests, camera-frame verification, real-vs-sim trajectory comparison, and VLA action-space mapping. `hardware_model_verified` remains false until this validation passes.

## 8. Legacy repository mapping

Legacy BracketBotCapstone examples remain conceptual references for depth, localization, path following, telepresence, realtime conversation, speech recognition, object detection/segmentation and manual drive. They must not be assumed to match the Hack the North 2026/commercial robot SDK unless Bracket Bot confirms compatibility.
