# VLA strategy for the Bracket Bot hospital application

## 1. Why a VLA layer is now justified

The supplied Meta Quest demo changes the technical assumptions of the project. The robot is not limited to navigation plus occasional rigid-object grasping: under teleoperation it can coordinate **two 7-DOF arms** on a deformable fabric task. The handout also explicitly positions the platform around `teleoperate -> collect data -> train -> deploy`.

That makes a Vision-Language-Action (VLA) policy a plausible execution layer for tasks where hand-authored grasp poses and deterministic waypoints do not generalize.

A VLA is **not** the top-level hospital decision-maker. It is a bounded visuomotor skill executor.

## 2. Hybrid autonomy architecture

```text
Patient/staff request
        |
        v
Request triage + hospital policy
        |
        v
Astra semantic/spatial planner
        |
        v
Skill Router
   /             \
  v               v
Deterministic     VLA policy
IK/motion          (bounded task)
planner             |
  \               /
   v             v
Deterministic Safety Supervisor
        |
        v
Bracket Bot SDK
        |
        v
Re-observe + verify
```

Fable remains an independent plan/policy critic for research and high-level validation; it is never a motor controller.

## 3. Tasks that probably do **not** need VLA

Prefer classical/deterministic control for:

- mapping/localization/navigation;
- driving to a known room/waypoint;
- room scanning;
- state-diff inspection;
- fixed-base camera positioning;
- known rigid-object grasp with validated pose;
- deterministic clear-zone checks;
- exact room-state templates with well-defined object geometry.

These are easier to validate and should remain the default when sufficient.

## 4. Tasks where VLA may create a real advantage

Research candidates, always inside hospital policy:

### 4.1 Cluttered personal-item retrieval
Examples: phone, glasses case, book, bag, remote. The problem is less “move gripper to pose X” and more “find the requested object, decide how it can be grasped, manage occlusion, and recover if the first grasp fails.”

### 4.2 Bimanual non-clinical handling
Examples in mock/skills-lab settings: arranging a clean bag, handling a clean linen item away from a patient, stabilizing an object with one arm while the other manipulates it.

### 4.3 Variable articulated objects
Approved drawers, handles, curtains/blinds or room fixtures can vary by hospital. A VLA can potentially generalize across geometry after enough demonstrations, while a strict pose script may need reprogramming room-by-room.

### 4.4 Visual-servo recovery
Wrist cameras make it possible for a policy to correct a near-miss grasp or compensate for small target motion without regenerating a full global plan.

### 4.5 Learned room-reset subtasks
If chairs, bags, linens or personal-item containers appear in many slightly different poses, a VLA can learn the invariant outcome while the room-state layer defines what “ready” means.

## 5. Tasks the VLA is forbidden to learn/execute in V1

- touching or repositioning a patient;
- manipulating medication;
- handling sharps;
- manipulating IV lines, oxygen, catheters or tubes;
- operating clinical device controls;
- silencing alarms;
- handling biohazards/bodily fluids;
- autonomous clinical assessment or treatment;
- any action near a patient where the deterministic human-clearance gate is not satisfied.

These restrictions are enforced outside the VLA and cannot be relaxed by model output.

## 6. Demonstration collection schema

Each Meta Quest teleoperation episode should be recorded as a synchronized trajectory:

```text
episode_id
task_text
task_class
room_id / scenario_id
timestamps
head_rgb
head_depth
left_wrist_rgb
right_wrist_rgb
base_pose
base_velocity
linear_stage_state
left_arm_q / qd
right_arm_q / qd
left_gripper_state
right_gripper_state
operator_action
safety_state
contacts/collisions if available
success
failure_reason
human_correction_events
```

Recommended additions once the SDK exposes them: end-effector wrench/force estimate, motor current/effort, gripper contact, localization covariance, and exact controller latency.

## 7. Data-collection protocol

### Stage A — clean demonstrations
Collect successful episodes from multiple operators in mock hospital rooms. Vary object position, orientation, lighting, clutter and starting base pose.

### Stage B — recovery demonstrations
Intentionally start from safe, imperfect states: partial grasp, object shifted, blocked approach, missed initial reach. Capture how operators recover.

### Stage C — negative / no-action examples
Include scenes where the correct result is **do not manipulate** because the object is prohibited, ambiguous, too close to a person, or not confidently identified.

### Stage D — policy rollouts + corrective teleop
Run the learned policy under supervision. When it hesitates or fails, switch to teleop, record the correction, and add that trajectory to the next training set.

This creates an iterative human-correction loop rather than one-shot training.

## 8. VLA training/evaluation loop

```text
Teleoperate
   -> record synchronized multimodal episodes
   -> privacy/safety filter
   -> quality label + task metadata
   -> train/fine-tune VLA on provided compute
   -> offline replay checks
   -> MuJoCo envelope/collision evaluation
   -> lab rollout behind safety supervisor
   -> corrective teleop
   -> retrain
   -> versioned policy promotion
```

The handout states that an 8× H100 shared node is available for policy training. The repository should treat that as an available event resource only after credentials/access are provisioned; no assumption is made about runtime quota or supported training framework.

## 9. MuJoCo's role with VLA

MuJoCo should be used for:

- dual-arm reachability;
- self-collision and environment collision;
- base/arm coordination;
- payload and stability envelopes;
- rigid-object contacts;
- domain randomization;
- safe workspace checks;
- regression evaluation between policy versions.

For fabric and other deformable/high-contact tasks, simulation can still provide useful constraints and approximate scenes, but it should **not** be treated as a perfect replacement for real robot demonstration data. The teleoperation demo is exactly why the project should preserve a real-data training path.

## 10. Runtime safety wrapper for a VLA

The VLA does not receive unrestricted actuator authority. Runtime must enforce:

1. hospital task allowlist;
2. object policy class;
3. person/patient proximity limits;
4. workspace/joint/action clipping;
5. self-collision and environment collision prediction;
6. bounded action horizon;
7. watchdog timeout;
8. E-stop availability;
9. anomaly/OOD stop;
10. post-action visual verification.

When confidence is low or the scene falls outside the policy's validated envelope, the system should switch to one of three outcomes: deterministic skill, human teleoperation, or staff escalation.

## 11. VLA evaluation metrics

Per task class:

- success rate;
- first-attempt success;
- human correction rate;
- intervention/teleop takeover rate;
- time to completion;
- number of grasp attempts;
- unexpected contacts;
- minimum person clearance;
- object drop rate;
- policy OOD/abstention rate;
- generalization to unseen object instances/layouts;
- sim-to-real performance gap;
- post-action verification success.

A policy can be technically impressive and still fail product acceptance if staff intervention or safety-stop rates are too high.
