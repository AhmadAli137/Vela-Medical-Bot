# Implementation status

## Implemented in this scaffold

- evidence-driven product specification;
- patient request Route A/B/C/D deterministic triage;
- room semantic state + desired-state models;
- room current-vs-desired diff engine;
- evidence-source registry and pain-point taxonomy;
- evidence opportunity scoring/ranking;
- authorized feedback CSV normalization pipeline;
- Astra structured feedback/scene/planning adapters;
- Fable structured independent critique adapters;
- deterministic safety policy;
- new Bracket Bot runtime capability abstraction;
- explicit refusal to map legacy capstone methods onto new hardware without vendor confirmation;
- MuJoCo MJCF hospital-room builder;
- non-vendor Bracket Bot placeholder strictly blocked from hardware approval (now known to require dual 7-DOF arms + shoulder linear stage in the execution-grade replacement);
- reviewed-image -> Astra scene annotation -> domain-randomized MuJoCo hypothesis-scene pipeline;
- FastAPI application layer;
- patient/staff browser console;
- FHIR Task stub;
- 50-hospital provenance-aware image acquisition configuration;
- six passing unit tests at packaging time.

## Not falsely represented as complete

- the 1,000-image corpus has **not been downloaded in this execution environment** because outbound bulk crawling/package setup is unavailable here;
- the user-provided Hack the North 2026 handout now confirms dual 7-DOF arms, 2 kg payload per arm, shoulder linear stage, floor-to-6-ft stated reach, head stereo-depth camera, per-arm wrist cameras, rotary pincher grippers, Jetson Orin Nano Super 8 GB, SLAM/navigation, Meta Quest teleoperation and VLA data/training/deployment; exact CAD/link geometry, joint/control limits, calibration, watchdog semantics and production SDK contract are still missing;
- the three supplied videos have now been reviewed: multi-camera views, mapping/navigation platform behavior, and bimanual deformable-fabric teleoperation materially expand the application assumptions;
- MuJoCo Python was not installed in this execution runtime, so generated MJCF was XML-generated/inspected but not physics-loaded here;
- no hospital integration, patient data, call-bell system, EHR, RTLS or live robot was connected;
- no claim of clinical efficacy, time savings or patient-experience improvement is made without a pilot.

## Required before real Bracket Bot manipulation

1. official vendor SDK;
2. vendor-accurate kinematic/collision model;
3. verified payload/reach/end-effector specs;
4. camera calibration and synchronization;
5. hardware E-stop/watchdog integration;
6. lab validation against real robot telemetry;
7. hospital-approved intended-use/risk analysis;
8. privacy/security and infection-prevention review;
9. human-factors/usability validation;
10. pilot with objective outcome metrics.


## Newly required VLA work

1. define the vendor action/observation interface once the production SDK is available;
2. record synchronized Meta Quest demonstration episodes in a mock hospital room;
3. add both wrist streams, head RGB-D, linear-stage state, both arms/grippers and base pose to the dataset schema;
4. implement policy versioning and a deterministic VLA safety wrapper;
5. build a dual-arm + linear-stage MuJoCo model;
6. add simulator regression suites for learned policies;
7. test human takeover/corrective teleoperation;
8. validate that VLA policies abstain on prohibited/ambiguous hospital objects.


## New evidence incorporated from supplied Bracket Bot materials

The architecture has been revised to reflect the uploaded Hack the North 2026 handout and three demos. Confirmed/observed capabilities now represented in the design include dual 7-DOF arms, vertical shoulder lift, 2 kg stated payload per arm, floor-to-6-ft stated reach, head stereo-depth vision, both wrist cameras, audio I/O, SLAM/navigation, Meta Quest teleoperation and the vendor-described VLA demonstration/training/deployment workflow.

The demos additionally support a design assumption that the hardware can generate coordinated bimanual trajectories on flexible objects **under teleoperation**. As a result, VLA training and supervised teleoperation are first-class development paths. They are not yet implemented against the real vendor SDK in this repository because the production action/state API, calibrated kinematic model and policy interface remain unavailable.

### Still required before real VLA execution
- vendor robot model (URDF/MJCF/CAD) and verified inertial/collision data;
- exact dual-arm + linear-stage state/action interface;
- synchronized head-depth + wrist-camera API and calibration;
- Quest teleoperation action representation and timestamps;
- vendor VLA deployment/runtime API or a supported policy-control bridge;
- real E-stop/watchdog/protective-stop integration;
- task-specific lab validation datasets.
