# HospitalBot Product + Application Specification

**Status:** research/MVP architecture, September 2026  
**Embodiment:** new Bracket Bot platform  
**Primary models:** GPT-6 Astra (`gpt-6-astra`) + Claude Fable 5 (`claude-fable-5`; 5.1 may be evaluated separately)  
**Physics:** MuJoCo 3.x / MJCF  
**Primary deployment boundary:** non-clinical patient-room and hospital operations

---

## 1. Product thesis

HospitalBot is an application layer for a general-purpose Bracket Bot that makes a hospital room **observable, queryable, assistive, and partially programmable** while keeping clinical judgment and high-risk physical actions with humans.

The core loop is:

`observe -> build world state -> understand request -> classify risk -> plan -> critique -> simulate -> approve -> act -> re-observe -> verify -> log`

The product is deliberately **not** another corridor delivery robot. Existing hospital robots already move medications, lab samples, supplies, and other payloads. The wedge here is the patient room itself:

1. reduce non-clinical interruptions to nurses;
2. give patients more independence over their immediate physical environment;
3. make routine hospital status information easier to obtain;
4. prepare/reconfigure rooms for approved operational states;
5. maintain a time-indexed semantic record of room state;
6. learn which physical and informational frictions create the most patient frustration or staff workload.

The long-term category is **adaptive physical environments**: software defines a desired physical state, and an embodied agent safely moves the current environment toward it.

---

## 2. Evidence-driven product development

The roadmap must not be selected by “what the robot can do.” It is selected by the intersection of three datasets:

### 2.1 Experience corpus
Patient comments, standardized patient experience measures, complaints, staff surveys, and clinician workload research answer:

- what repeatedly frustrates patients;
- which routine needs create staff interruptions;
- where waiting and uncertainty are worst;
- which environmental factors materially affect the inpatient experience;
- where nurses and physicians report overload.

### 2.2 Physical-environment corpus
At least 1,000 candidate hospital-room images from at least 50 named hospitals, plus licensed/open datasets and synthetic scenes, answer:

- what objects appear in rooms;
- how room layouts vary;
- which objects are commonly movable;
- what spatial constraints recur;
- which visual domains perception must handle.

### 2.3 Robot capability corpus
The user-provided Hack the North 2026 handout and demos now establish a substantially richer robot envelope than the earlier public-site-only research suggested. Confirmed planning-level capabilities include:

- custom 180° stereo depth head camera, stated 2560×960 video;
- camera on **each wrist/arm** for visual servoing;
- **dual 7-DOF arms** with custom IK;
- independent shoulder vertical linear stage;
- stated reach from the floor to approximately 6 ft height;
- **2 kg payload per arm**;
- rotary pincher grippers driven by a stated 50 kg·cm stall-servo mechanism;
- speaker + microphone, with AEC stated for the speaker;
- Jetson Orin Nano Super 8 GB onboard compute;
- hub BLDC drive motors, stated 8.5 N·m;
- SLAM, localization and autonomous movement out of the box;
- Meta Quest teleoperation;
- first-class `teleoperate -> collect data -> train -> deploy` VLA workflow;
- stated shared 8× NVIDIA H100 node for policy training.

The supplied demos further show simultaneous head + left/right wrist-camera views, mobile mapping/navigation in a cluttered environment, and **bimanual teleoperated manipulation of deformable fabric**. That last demo proves hardware dexterity under human control, not autonomous dexterity, and motivates a VLA training path.

Still required from the production robot/runtime before execution-grade simulation: exact CAD/link geometry, joint/velocity/effort limits, gripper geometry, camera calibration, base dimensions/kinematics, control modes, watchdog/protective-stop semantics, and actual SDK calls.

The product opportunity score is computed only where patient/staff need, room/environment evidence, and robot capability overlap.

---

## 3. Current evidence: patient and staff problems to prioritize

### 3.1 Patient themes
The 2024 NHS Adult Inpatient qualitative work identified six top-level themes across written responses: gratitude, staff, waiting, communication, hospital environment/facilities, and discharge/aftercare. Subthemes included being informed, staff capacity, bed availability, noise, privacy, sensory issues, transport, and aftercare.

Robot-addressable portions include:

- **lack of information / uncertainty:** “what happens next?”, status of transport, whether a request has been received;
- **slow response to simple non-clinical requests:** retrieving a personal object, repositioning an approved table/chair, finding a mobility aid, environmental control;
- **environmental autonomy:** blinds, lighting, entertainment interface, approved room controls;
- **noise awareness:** locating avoidable non-clinical sources or notifying staff, without silencing medical alarms;
- **room readiness:** clear pathways, misplaced non-clinical objects, missing approved equipment;
- **discharge logistics:** locate wheelchair/approved transport equipment, check personal-item area, display verified process status;
- **language/interface accessibility:** multilingual conversational interface, captions/text UI, simple visual prompts, without replacing clinical interpretation services where policy requires a qualified interpreter.

### 3.2 Nurse pressures
Relevant survey structures repeatedly measure:

- staffing/work pace;
- interruptions and task overload;
- handoffs/information exchange;
- emotional exhaustion/burnout;
- workplace safety;
- time spent away from direct patient care on routine logistics.

The robot should therefore target **small but frequent, non-clinical work** rather than trying to automate nursing practice.

### 3.3 Physician pressures
Canadian physician evidence strongly points to administrative burden and fragmented information as major pressures. The robot should not attempt diagnosis; its physician value proposition is:

- make rooms physically ready before rounds/procedures;
- surface verified operational information without adding a new inbox;
- execute explicitly assigned non-clinical follow-through;
- reduce time spent finding people/items/status;
- create structured event logs that can feed existing hospital systems.

---

## 4. Product surfaces

HospitalBot has four application surfaces.

### 4.1 Patient Room Agent
A bedside conversational + physical assistant for **non-clinical** needs.

Core commands:

- “Where is my phone/glasses/bag?”
- “Can you bring that approved personal item closer?”
- “Can you move the approved tray/table/chair?”
- “Can you close/open the blinds?” when connected to an approved interface or physically supported mechanism;
- “What is happening next?” -> only answer from hospital-authoritative operational sources;
- “Has my nurse received my request?” -> show request state;
- “Can you call my nurse?” -> create/route a request, not imply clinical triage was completed;
- “Can you help me video call my family?” -> launch an approved communications workflow;
- “I need medical help” -> immediate escalation; robot does not assess whether the need is medically urgent unless a hospital-approved emergency workflow explicitly handles routing.

### 4.2 Staff Copilot
A voice/mobile/web interface for nurses, physicians, aides, EVS, porters, rehab staff, and unit clerks.

Examples:

- “Check whether 417 matches the approved physio setup.”
- “Find the wheelchair assigned to this unit.”
- “Prepare the non-clinical room layout for rounds.”
- “Return approved movable objects to the default room state.”
- “Show me unresolved non-clinical patient requests.”
- “Which rooms have blocked clear zones?”
- “What changed in 417 since the last verified snapshot?”

### 4.3 Fleet / Operations Console
For charge nurses, managers, robotics operations, and facilities.

Views:

- fleet status / battery / connectivity;
- unit-level task queue;
- room state and desired-state compliance;
- escalations;
- rejected actions and safety reasons;
- map/world-model freshness;
- utilization and staff-minutes returned;
- patient request category trends;
- simulator/replay view;
- evidence/research dashboard showing why features are prioritized.

### 4.4 Research + Simulation Studio
For developers/researchers, never exposed as a clinical operator control surface.

Functions:

- import hospital imagery and scene annotations;
- generate parametric MuJoCo rooms;
- perturb layouts;
- test robot embodiments;
- test action plans under uncertainty;
- replay captured room states;
- score perception, planning, reachability, collision margins, and policy behavior;
- generate synthetic training/evaluation episodes.

---

## 5. The request router: the key patient-experience primitive

Every spoken/tapped patient request is first classified into one of four routes.

### Route A — Self-service informational
Examples: approved visitor hours, request status, how to use room Wi-Fi, operational schedule information supplied by hospital systems.

Action: answer from authoritative hospital source; cite/source the information in staff logs; do not improvise medical information.

### Route B — Robot-resolvable non-clinical physical
Examples: move an approved personal object; position an approved movable table; adjust an integrated non-clinical room control.

Action: perception -> object policy -> plan -> simulation -> safety gates -> execution -> verification.

### Route C — Human non-clinical
Examples: food issue, cleaning request, missing linen, equipment request beyond robot capability.

Action: create/route task to correct hospital service and confirm that the request was sent.

### Route D — Clinical / uncertain / urgent
Examples: pain, new symptoms, medication questions, patient says they feel unwell, attached line/device issue, fall risk concern.

Action: **do not answer clinically**. Route to approved clinical escalation workflow. Maintain conversational presence only to confirm help was requested and, if allowed, provide status.

A deterministic keyword/rule layer must be able to override model classification toward Route D. AI may escalate more conservatively but never downgrade a deterministic clinical/urgent trigger.

---

## 6. Room state model

A RoomState is a timestamped, versioned semantic + geometric description, not a raw photograph.

It contains:

- room coordinate frame;
- calibrated robot pose;
- object instances;
- object categories;
- metric 3D bounds where available;
- pose confidence;
- movability estimate;
- object policy class;
- relationships (on, under, beside, attached-to, blocks, within-reach-zone);
- free-space map;
- keep-clear zones;
- human-presence regions;
- hospital-defined room mode;
- source sensor frame IDs;
- uncertainty provenance.

### Object policy classes

1. `clinical_prohibited`: medication, sharps, IV/oxygen/tubes, attached clinical devices, alarm controls, unknown patient-connected items.
2. `staff_only`: hospital asset that may move only under staff workflow.
3. `observe_only`: safe to see/track but not touch autonomously.
4. `manipulable`: explicitly allowlisted object class + specific instance cleared for the current task.

**Unknown defaults to observe-only.**

---

## 7. Desired room states (“physical programs”)

Approved templates describe outcomes rather than motor sequences.

Examples:

- `admission_ready`
- `rounds_ready`
- `physio_ready`
- `meal_ready`
- `visitor_ready`
- `rest_state`
- `turnover_nonclinical_ready`
- `default_room_state`

Each template may define:

- required/forbidden object classes;
- acceptable position regions, not necessarily exact coordinates;
- minimum clearances;
- required clear walking/working zones;
- room-control settings;
- prohibited robot interactions;
- who can approve the transition;
- maximum manipulation risk class.

The robot compares current vs desired state, produces a physical diff, and proposes the smallest reversible set of changes.

---

## 8. “Git for the room” temporal model

Each verified snapshot creates a version:

`Room 417 / 2026-09-12T18:04:10`

Diffs include:

- object appeared/disappeared;
- object pose changed;
- cabinet/door state changed;
- clear zone became blocked/unblocked;
- approved room-control state changed;
- object policy changed;
- perception confidence changed materially.

The system stores **semantic deltas**, not indefinite raw patient video by default.

Use cases:

- “What changed since EVS completed turnover?”
- “Why is this room not ready?”
- “Which object prevents the physio template from passing?”
- “Restore only the approved non-clinical objects to the previous verified state.”

There is no blind “restore” command. Every reverse action is replanned against the current environment and current safety policy.

---

## 9. AI responsibilities

### 9.1 GPT-6 Astra
Use Astra for tasks where spatial/visual/world reasoning and long-context synthesis are valuable:

- scene-semantic extraction from approved imagery;
- room-state interpretation from fused perception output;
- high-level task decomposition;
- desired/current-state diff reasoning;
- question answering over hospital-approved operational context;
- research-corpus coding/clustering;
- generating simulation test cases;
- explaining plans to staff.

Astra receives **no raw torque/PWM/current tools**.

### 9.2 Claude Fable 5
Use Fable as an independent second-model reviewer for consequential plans and research analysis:

- challenge hidden assumptions;
- identify possible clinical boundary violations;
- identify missing object properties;
- propose additional simulation perturbations;
- critique whether a feature really addresses the patient/staff pain point;
- audit evidence synthesis for unsupported claims.

Fable is not the safety kernel and cannot approve hardware execution.

### 9.3 VLA skill layer

The new Bracket Bot explicitly supports demonstration collection, VLA training and policy deployment, and the Meta Quest demo shows why this matters: two arms can be coordinated on a deformable-object task that would be awkward to encode as fixed grasp poses.

The VLA is a **bounded skill executor**, not the hospital decision-maker. It is used only when:

- the request has already passed Route A/B/C/D triage;
- the target object/action class is allowlisted;
- deterministic navigation/world-state services have localized the task;
- the policy version is approved for that task class;
- human/patient clearance is satisfied;
- the safety supervisor can constrain and stop the rollout.

VLA candidates include cluttered personal-item retrieval, bimanual handling of approved non-clinical objects, variable articulated fixtures, and wrist-camera-driven grasp recovery. Navigation, room scans, state diffs and known rigid-object trajectories should remain deterministic when practical.

The VLA observation stream can combine head RGB/depth, both wrist cameras, base pose, linear-stage state, arm/gripper proprioception and the language task. Meta Quest teleoperation provides aligned action demonstrations. See `VLA_STRATEGY.md`.

### 9.4 Deterministic safety kernel
The final authority over execution. It evaluates:

- task allowlist;
- object policy;
- capability availability;
- hospital/room policy;
- human proximity;
- verified robot model status;
- trajectory collision results;
- force/speed/clearance envelopes;
- required human approvals;
- watchdog/estop status;
- network-independent stop behavior.

---

## 10. Model orchestration pattern

### Low-risk perception/information task

`request -> deterministic triage -> Astra -> source validation -> answer/log`

### Manipulation task — deterministic skill

`request -> deterministic triage -> Astra plan -> Fable critique when enabled -> deterministic IK/motion planner -> MuJoCo -> safety kernel -> robot -> post-action verification`

### Manipulation task — VLA skill

`request -> deterministic triage -> Astra task/target grounding -> skill router -> approved VLA policy -> bounded rollout -> deterministic action envelope / person-object policy / collision checks -> robot -> head+wrist re-observation -> verify/continue/stop`

The VLA may be replaced by live Meta Quest teleoperation whenever the policy is outside its validated envelope or an authorized operator chooses supervised control.

### Clinical/uncertain task

`request -> deterministic clinical gate -> approved hospital escalation -> patient acknowledgement/status`

No generative model can bypass a failed deterministic gate.

---

## 11. Bracket Bot integration contract

### Confirmed Hack the North 2026 platform envelope

For product design, model the robot as a **mobile, vertically extensible, dual-arm manipulator** rather than a wheeled camera platform. The supplied handout specifies two 7-DOF arms, 2 kg payload per arm, a shoulder linear lift, floor-to-6-ft stated reach, head stereo-depth perception, a wrist camera per arm, rotary pincher grippers, audio I/O, onboard Jetson compute, SLAM/navigation, Meta Quest teleoperation and a VLA training/deployment path.

The simulator and app must therefore support `base + lift + left arm + right arm + two grippers + head RGB-D + two wrist cameras` as the minimum logical embodiment.

The supplied videos show three important platform behaviors: multiple onboard camera viewpoints, mobile mapping/navigation with a live 3D map, and bimanual deformable-fabric manipulation under teleoperation. These observations expand the application scope, but teleoperated capability is not treated as autonomous capability.

The application defines a stable internal interface:

- `discover_capabilities()`
- `observe_room()` / synchronized head+wrist observations
- `get_base_pose()`
- `navigate_to_semantic_target()`
- `get_linear_stage_state()`
- `get_arm_state(arm)`
- `execute_verified_trajectory()`
- `operate_verified_end_effector()`
- `start_teleoperation()` / `record_demonstration()`
- `execute_approved_vla_skill()` through the deterministic safety supervisor
- `speak()` / `listen_stream()`
- `stop()` / `hold()`

The vendor adapter binds these only when the production runtime proves the primitive exists. Astra/Fable never call them directly.

### Required capability handshake before manipulation

- exact base kinematics/dimensions known;
- robot collision model hash verified;
- shoulder linear-stage travel and limits known;
- both 7-DOF arms' joint names/axes/limits/control modes known;
- joint position/velocity/acceleration/effort limits known;
- both gripper geometries/states/limits known;
- payload/reach limits validated against the shipped revision;
- head stereo/depth and both wrist cameras calibrated and synchronized;
- emergency stop primitive verified;
- watchdog heartbeat and protective-stop semantics verified;
- vendor VLA/teleoperation action representation known if used;
- exact SDK command/feedback rates known.

Until then, the simulator may be used only as a software/surrogate research environment.

---

## 12. MuJoCo architecture

MuJoCo represents **contact-relevant geometry and dynamics**, not the complete photorealistic hospital.

### 12.1 Scene layers

1. **Static shell:** floor, walls, doorway, fixed cabinets, built-ins.
2. **Clinical obstacles:** bed and clinical equipment represented conservatively as non-manipulable collision geometry.
3. **Approved movable objects:** chair, table, personal-item container, approved cart, etc.
4. **Human safety volumes:** simplified dynamic exclusion geometry driven by current perception or replay traces.
5. **Bracket Bot:** vendor-accurate MJCF/URDF-converted model once supplied. Until then, explicit placeholder/surrogate.
6. **Sensors:** virtual head stereo/depth plus left/right wrist cameras for perception and VLA regression; real execution geometry still comes from calibrated robot perception.

### 12.2 Simulation purposes

- scene/model validity;
- reachability;
- self-collision;
- environment collision;
- base placement feasibility;
- object stability;
- grasp/placement feasibility;
- clearance margin;
- parameter sensitivity;
- safe failure/recovery;
- task success under layout perturbation.

### 12.3 VLA / teleoperation simulation support

MuJoCo is not only a pre-action checker. It should also be the regression environment for learned skills:

- replay recorded base/lift/arm trajectories;
- test dual-arm self-collision and reachability;
- randomize room layout, object pose, mass and friction;
- test rigid-object grasp/action envelopes;
- expose head and wrist virtual cameras to a policy where useful;
- compare policy versions on identical scenario suites;
- inject safe perturbations and evaluate recovery/abstention.

For cloth/linens and other deformable/high-contact tasks, simulation is an approximation. The supplied Meta Quest demo shows a real-data route that should remain central: collect demonstrations on the physical robot, use MuJoCo for safety geometry and complementary domain randomization, and validate learned policies on the robot under supervision.

### 12.4 Not simulated from web photographs

Do not infer exact:

- object mass;
- coefficient of friction;
- center of mass;
- hinge torque;
- structural attachment;
- patient condition;
- safe clinical interaction.

Use explicit parameter distributions and identify unknowns through measurement/system identification only in approved testing environments.

---

## 13. Real-to-sim pipeline

### Offline hospital image pipeline

`official/public page -> candidate image -> provenance + hash -> privacy/rights quarantine -> human approval -> Astra semantic annotation -> aggregate scene priors -> parametric MuJoCo generation`

### Live room pipeline

`calibrated RGB/depth + localization -> geometric reconstruction -> instance tracking -> semantic policy labels -> RoomState -> simulation scene`

Live robot execution must never depend on single-image monocular metric guesses when depth/calibrated measurements are needed.

---

## 14. Hospital image corpus requirements

Target: **>=1,000 candidate room images across >=50 hospitals**, with a balancing target of >=20 per named hospital.

The provided manifest currently enumerates 50 Canadian and U.S. hospitals/health systems. The crawler:

- stays on configured domains;
- obeys robots.txt;
- rate-limits;
- does not bypass authentication/anti-bot systems;
- records provenance;
- hashes/deduplicates;
- rejects tiny/non-image content;
- places all results in quarantine;
- requires manual rights/privacy review before use.

The corpus is for room/object/layout priors and perception evaluation—not for redistribution and not automatically for commercial model training.

---

## 15. Patient/staff evidence corpus

### Source classes

- **NHS Adult Inpatient Survey qualitative report:** thematic/free-text evidence.
- **CMS HCAHPS:** standardized hospital-level patient experience dimensions.
- **CIHI CPES-IC:** Canadian inpatient experience measures and historical comparative data.
- **Care Opinion:** narrative stories/tags under subscription/API and CC BY-NC-SA constraints; commercial use requires appropriate permission/licensing.
- **NHS Staff Survey:** very large staff-experience dataset and downloadable spreadsheets.
- **AHRQ Hospital SOPS:** staffing/work pace, teamwork, communication, handoffs and safety culture; research respondent-level data available by application.
- **CMA physician surveys:** workload, burnout, EMR/admin burden.
- **CFNU nurse survey:** Canadian nursing work-life pressures.
- **Ontario Patient Ombudsman:** complaint-level thematic/annual-report evidence relevant to local deployment context.

### Normalized pain-point record

Each record contains:

- stakeholder role;
- source and provenance;
- verbatim text only when reuse rights permit;
- otherwise paraphrase/theme only;
- theme/subtheme;
- frequency/support strength;
- severity;
- time cost;
- patient frustration;
- staff interruption likelihood;
- physical-action requirement;
- navigation requirement;
- manipulation requirement;
- conversation/information requirement;
- clinical risk;
- robot addressability;
- proposed intervention;
- evidence confidence;
- commercialization/licensing note.

---

## 16. Opportunity ranking

Do not rank purely by frequency. Score each pain point on:

- `evidence_strength` (0-5)
- `patient_impact` (0-5)
- `staff_time_pressure` (0-5)
- `physical_embodiment_advantage` (0-5)
- `technical_feasibility` (0-5)
- `workflow_integration_feasibility` (0-5)
- `measurability` (0-5)
- `clinical_risk` (0-5, subtract)
- `regulatory/privacy_complexity` (0-5, subtract)
- `competitive_crowding` (0-5, subtract)

Recommended composite:

`score = 1.4*evidence + 1.5*patient + 1.5*staff + 1.7*embodiment + 1.2*technical + integration + measurability - 2*risk - privacy - crowding`

The weights are product hypotheses and must be validated with hospitals.

---

## 17. Initial ranked feature hypotheses

### Tier 1 — build first

1. **Patient request router + status**  
   Answers verified operational questions, routes clinical requests, handles approved non-clinical tasks, shows request status.

2. **Personal-item reach assistance**  
   Identify and retrieve/reposition explicitly safe personal objects in a mock room; live pilot requires rigorous object policy and human-proximity constraints.

3. **Room-state scan and clear-zone verification**  
   Perception-only initially. High feasibility and useful to staff without manipulation risk.

4. **Approved room-mode readiness**  
   “Is the room ready for physio/rounds/meal/visitor?” first as check-only, then limited corrective manipulation.

5. **Find/locate non-clinical mobile equipment**  
   Richer than a delivery workflow because room state and semantic context are maintained.

### Tier 2 — after reliability

**VLA-enabled manipulation candidates** should enter only after the deterministic navigation, world-state and safety stack is reliable. Early candidates include retrieval from clutter, variable grasps of approved personal items, bimanual handling of approved clean non-clinical objects, and visually guided recovery using the wrist cameras. Each VLA capability is promoted task-by-task from teleoperation demonstrations; there is no blanket “general autonomy” switch.


6. **Approved object repositioning**  
   Chair/table/tray/cart classes under explicit allowlists and staff configuration.

7. **Patient environment controls**  
   Via authorized building/smart-room interfaces where possible; physical manipulation only as secondary path.

8. **Discharge logistics assistant**  
   Wheelchair/equipment location, belongings checklist area, transport status, but no clinical discharge decisions.

9. **Automatic room-state restoration**  
   Restore approved non-clinical objects to a verified template; never touch clinical/patient-connected equipment.

### Tier 3 — research

10. **Predictive resource staging**  
    Learn temporal demand for wheelchairs/carts/room modes; require hospital operations validation.

11. **Multi-robot room/floor coordination**

12. **Cross-room physical operations optimizer**

---

## 18. Patient experience design principles

- Never pretend to be a nurse/doctor.
- Be explicit about what was sent vs completed.
- Never fabricate wait times.
- Use calm, short responses in patient rooms.
- Provide screen/text alternatives to voice.
- Do not use facial recognition for patient identity.
- Do not infer sensitive attributes from appearance or voice.
- Use hospital-provided identity/session context only when authorized.
- Include “stop”, “go away”, and privacy controls that are immediate and understandable.
- Default cameras/audio to the minimum retention required for function and safety.
- Prefer on-device processing and semantic event storage when feasible.

---

## 19. Staff experience design principles

- Do not create another dashboard staff must constantly monitor.
- Voice/task assignment should be possible in seconds.
- Escalations go into existing workflows where possible.
- Every autonomous action must be inspectable after the fact.
- Show why an action was blocked, not just “failed.”
- Staff can mark an object “never touch,” a region “no robot,” or a task “human only.”
- Unit managers can pause all manipulation while retaining observation/information features.

---

## 20. Hospital integration layer

### FHIR / EHR integration
Use narrowly scoped, hospital-approved FHIR resources where appropriate:

- `Task` for operational work;
- `Location` for room/unit metadata;
- `Encounter` only for authorized context needed to associate a patient-room session;
- `PractitionerRole` / care-team context where required;
- `Communication` or approved messaging integration for status where hospital policy permits.

Do not make the robot an EHR system of record.

### RTLS / asset management
Integrate with existing RTLS when available rather than replacing it. The robot adds visual/contextual state such as “wheelchair appears unused next to Room 417” but RTLS remains authoritative for asset identity if that is hospital policy.

### Nurse call
Integrate to submit/acknowledge routing; never suppress or intercept existing safety-critical call pathways.

### Building/smart-room systems
Prefer digital integrations for lights/blinds/TV/HVAC over physical actuation when secure, supported interfaces exist.

---

## 21. Security and privacy

### Data classes

- **Class 0:** public research data.
- **Class 1:** facility map/asset configuration.
- **Class 2:** room interaction metadata.
- **Class 3:** patient-linked operational data.
- **Class 4:** raw patient-room audio/video, highest restriction.

### Controls

- mutual TLS between robot and hospital edge;
- device identity and hardware-backed key storage where possible;
- least-privilege service accounts;
- short-lived tokens;
- strict network egress policy;
- encryption at rest/in transit;
- audit log for access and physical actions;
- raw video/audio retention off by default unless a defined workflow needs it;
- redaction at ingestion for research datasets;
- explicit separation between model telemetry and hospital data;
- vendor/API data handling reviewed for healthcare use before any real patient data is sent externally.

For eligible OpenAI API customers, Astra documentation states Zero Data Retention support is available; eligibility and exact deployment terms must be confirmed contractually before hospital use. Anthropic documents model-specific retention requirements for Fable 5; these must be reviewed and may affect whether Fable can process live patient-linked content. A safe architecture can keep Fable on de-identified/offline plan-review tasks if necessary.

---

## 22. Safety invariants

The following are prohibited for autonomous V1:

- touching a patient;
- supporting patient body weight;
- medication handling/selection/administration;
- sharps handling;
- IV, catheter, oxygen, tubing, drains, lines or patient-connected device interaction;
- silencing or altering clinical alarms;
- changing clinical device settings;
- medical diagnosis or treatment advice;
- autonomous restraint;
- moving the hospital bed while occupied;
- opening unknown clinical containers;
- manipulating unknown objects;
- operating in a person-contact trajectory without a separately validated safe mode.

The application should fail toward **ask/route/stop**.

---

## 23. Acceptance metrics

### Patient-facing

- non-clinical request resolution rate;
- median request-to-resolution time;
- percentage of requests resolved without interrupting clinical staff;
- request routing accuracy, with special focus on zero unsafe clinical downgrades;
- patient-reported ease of getting information;
- autonomy/usability rating;
- number of unwanted robot interactions/privacy complaints.

### Staff-facing

- staff minutes returned per shift;
- interruptions avoided;
- room-check time reduced;
- time spent searching for equipment;
- manual corrections per robot task;
- blocked unsafe actions;
- staff trust / willingness to delegate.

### Robotics

- semantic object precision/recall;
- room-state diff precision/recall;
- localization uptime;
- plan success rate;
- reachability prediction accuracy;
- collision/near-collision rate;
- minimum observed clearance;
- grasp/placement success;
- false “task complete” rate;
- recovery success;
- intervention rate;
- VLA task success by policy/version;
- VLA abstention / OOD rate;
- teleoperation takeover rate;
- corrective-demonstration frequency;
- VLA generalization to unseen object instances/layouts.

---

## 24. MVP phases

### Phase 0 — evidence + digital-only

- build pain-point corpus;
- rank opportunities;
- 1,000/50 image candidate collection pipeline;
- parametric room generator;
- Bracket Bot surrogate/placeholder simulation;
- operations console;
- no real patient data.

### Phase 1 — mock hospital room, observation only

- new Bracket Bot with calibrated sensors;
- scene graph;
- room snapshots/diffs;
- patient/staff voice UI with scripted/mock hospital systems;
- no autonomous manipulation.

### Phase 2 — mock room, constrained manipulation

Allowlist 3-5 objects such as an empty lightweight personal-item bin, visitor chair proxy, movable table proxy, and simple switch/blind mockup. Validate with vendor robot model.

### Phase 2.5 — teleoperation dataset + bounded VLA

- use Meta Quest control to record synchronized head/wrist/proprioceptive demonstrations in a mock hospital room;
- start with non-clinical object retrieval and room-reset subtasks;
- collect successful, recovery and no-action demonstrations;
- train/fine-tune a task-bounded VLA using the provided training workflow/compute if access is available;
- evaluate offline, in MuJoCo, and then on the real robot behind the deterministic safety supervisor;
- measure human takeover rate and policy abstention, not just task success.

### Phase 3 — simulation + clinical skills lab

Partner with hospital simulation centre. No real patients. Test workflows with nurses, patients/advisors, rehab staff, infection prevention, privacy/security and biomedical engineering.

### Phase 4 — live observational pilot

Real unit, observation/information/routing only. Shadow mode for manipulation.

### Phase 5 — limited non-clinical actuation pilot

Only after safety case, institutional approval, vendor constraints, human factors testing, and hospital governance.

---

## 25. Competitive differentiation

Moxi 2.0 now advertises a robotic World Model and improved manipulation for hospital logistics. Therefore **“world model for hospitals” is not a differentiator**.

HospitalBot differentiation must be measurable around:

1. **patient-room rather than corridor logistics**;
2. **patient experience + staff interruption reduction**;
3. **current-state vs desired-state physical programming**;
4. **runtime real-to-sim verification for manipulation**;
5. **temporal room-state diff and verification**;
6. **evidence-driven feature prioritization based on patient/staff datasets**;
7. **platform layer on a low-cost developer robot rather than a proprietary single-purpose hospital robot**.

---

## 26. First signature demo

A mock inpatient room contains:

- hospital-bed prop (prohibited/observe-only);
- visitor chair;
- rolling table prop;
- personal-item bin;
- phone prop positioned differently each run;
- window/blind mockup;
- wheelchair/cart prop;
- clean fabric/bag prop for a controlled bimanual task;
- keep-clear zone;
- staff tablet;
- authorized Meta Quest teleoperation station.

Recommended sequence:

1. Bracket Bot maps/localizes in the mock room using its platform navigation stack.
2. It builds a metric semantic scene from head stereo/depth plus wrist observations as needed.
3. Patient asks, “Can you bring my phone closer?” with the phone in a non-scripted pose.
4. Astra grounds the request and target; the skill router selects a deterministic grasp if the geometry is known, otherwise a validated bounded VLA skill.
5. Safety supervisor enforces prohibited-object and person-clearance zones; head+wrist cameras verify the grasp and placement.
6. Patient asks, “When is my scan?” and receives only mocked authoritative workflow status.
7. Patient says, “My chest hurts.” Deterministic clinical escalation overrides any self-service behavior; the robot performs no clinical analysis.
8. Staff asks, “Prepare this room for physio.” The system compares current vs desired state and repositions only allowlisted props.
9. A controlled second task demonstrates two-arm manipulation on a clean non-clinical flexible object.
10. If the learned skill fails or abstains, an authorized operator takes over through Meta Quest; the corrective episode is saved as VLA training data.
11. Robot re-observes the room and verifies the desired-state predicates.
12. Research console shows the full learning loop: `teleoperate -> collect -> train -> evaluate -> deploy -> correct -> retrain`.

This demonstrates the whole thesis: **understand -> communicate -> simulate -> act -> verify -> remember**, without pretending the robot practices medicine.

---

## 27. What would make this venture-scale

The long-term asset is not the Bracket Bot unit. It is the continuously improving representation of **how human spaces should be configured, what changes, what people request, and what physical interventions safely resolve those requests**.

If the hospital wedge works, the same core engine can target classrooms, laboratories, warehouses, hospitality, and escape-room/reset workflows through different policy packs and desired-state libraries.

The common platform is:

`physical state + temporal memory + intent + simulation + safe actuation + verification`.


## 18. Expanded Bracket Bot capability envelope after handout + demo review

The supplied Hack the North handout and demos substantially expand the feasible application layer. The robot should no longer be modeled as a wheeled platform that occasionally performs a grasp. It should be treated as a **mobile, bimanual, vertically extensible manipulation platform with three simultaneous visual viewpoints and a built-in demonstration-learning workflow**.

### 18.1 Capability classes

| Capability class | Hardware / platform basis | Hospital opportunity | Preferred autonomy path |
|---|---|---|---|
| Wide-area perception | Head stereo-depth camera + SLAM | room scan, obstacle/clear-zone checks, locating large objects, navigation | deterministic perception + Astra semantics |
| Fine manipulation perception | left/right wrist cameras | close-range grasping, visual servoing, recovery from occlusion | deterministic visual servo or VLA |
| Bimanual manipulation | dual 7-DOF arms | stabilize-and-manipulate, large/light objects, bags, clean linens, multi-step room reset | bounded VLA often appropriate |
| Vertical workspace access | independent shoulder linear stage, stated floor-to-6-ft reach | floor pickup, bedside surfaces, shelves/cabinets within validated limits | deterministic stage + IK, VLA for variable contact |
| Voice interaction | microphone + speaker/AEC | patient requests, staff commands, clarification, teleop handoff | deterministic request router + Astra |
| Mobile manipulation | autonomous base + two arms | search, retrieve, deliver-to-surface, room reset, multi-room tasks | navigation deterministic; manipulation hybrid |
| Demonstration learning | Meta Quest custom IK + VLA workflow | rapid task teaching, corrective demonstrations, site-specific skills | teleop -> dataset -> VLA -> supervised promotion |

### 18.2 Hospital task portfolio: what becomes possible

These are **research/product candidates**, not claims that the robot already performs them autonomously. Each task must be promoted through simulation, supervised lab trials, teleoperation, and task-specific safety validation.

#### Tier 0 — deterministic / low-manipulation
- conversational patient request intake and routing;
- autonomous room-to-room navigation;
- room scans and semantic state diffs;
- locating approved non-clinical objects;
- status display / explanation from authoritative hospital systems;
- staff telepresence and remote inspection;
- escorting a staff member or guiding them to an item/location.

#### Tier 1 — rigid-object manipulation, usually classical first
- pick up and place approved personal items such as a phone, glasses case, remote, book or small bag;
- move an approved item from floor to a bedside surface;
- place returned belongings into an approved zone;
- operate a known drawer or cabinet with validated geometry;
- reposition approved lightweight room accessories;
- retrieve small non-clinical supplies from a known location;
- press or actuate specifically allowlisted non-clinical controls where hospital policy permits.

#### Tier 2 — variable manipulation where VLA is likely valuable
- retrieve a requested object from clutter or partial occlusion;
- choose a grasp for unseen instances of an allowlisted object class;
- open drawers/cabinets/curtains with variable geometry;
- visually recover from a missed or shifted grasp using wrist cameras;
- manipulate a bag while stabilizing it with the second arm;
- arrange multiple approved room objects to match a desired room state;
- transfer an object between arms when useful for reach/orientation;
- perform multi-step room-reset subtasks that differ from room to room.

#### Tier 3 — bimanual / deformable-object skills, VLA-first research
The Meta Quest demo demonstrates that the hardware can be teleoperated through coordinated bimanual handling of flexible fabric. That makes the following worth researching in **mock or unoccupied-room settings**:

- fold or stage clean linens away from a patient;
- place a clean blanket or sheet onto an unoccupied surface/bed for room preparation;
- organize a patient's bag or clothing on an approved surface, only with explicit permission and no direct patient contact;
- open/hold a soft bag while placing an approved object inside;
- straighten or gather non-clinical fabric items during room reset;
- handle lightweight awkward objects that benefit from two-arm stabilization.

These skills should not be assumed from the teleoperation demo. The demo proves **hardware dexterity and a viable demonstration-collection mechanism**, not autonomous deformable-object competence.

### 18.3 Tasks that remain out of scope even if a VLA can physically perform them

The ability to learn an action does not make the action appropriate. V1/V2 must continue to prohibit:

- touching, lifting, repositioning, feeding, dressing, or physically supporting a patient;
- manipulating medication, sharps or biohazards;
- manipulating IV lines, oxygen, catheters, drains or other attached clinical equipment;
- operating or silencing clinical-device controls/alarms;
- autonomous clinical examination, diagnosis or treatment;
- any manipulation where a patient is inside the validated exclusion zone.

### 18.4 Autonomy promotion ladder

Every new manipulation skill should progress through the same ladder:

`manual concept -> Meta Quest teleoperation -> synchronized demo dataset -> offline replay -> MuJoCo envelope tests -> bounded VLA policy -> lab supervised rollout -> corrective teleop -> repeated safety/effectiveness validation -> limited pilot -> production`

No skill jumps directly from a language-model plan to real hardware autonomy.

### 18.5 Why the VLA matters to the product thesis

Without a VLA, the product risks becoming a collection of individually engineered grasps and room-specific scripts. With a bounded VLA layer, the product can instead learn reusable skills such as **retrieve, open, arrange, stabilize, hand over to a surface, and reset** across different rooms and object instances. The hospital application layer still owns the goal, permissions, patient/staff context, safety constraints and verification; the VLA owns only the short-horizon visuomotor execution of an approved skill.
