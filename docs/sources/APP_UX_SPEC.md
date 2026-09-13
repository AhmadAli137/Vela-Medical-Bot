# HospitalBot application UX specification

## Design principle

The robot should feel like **one quiet operational layer**, not another hospital dashboard demanding attention. Staff surfaces are exception-driven; patient surfaces are simple, accessible and transparent about what the robot can and cannot do.

## 1. Patient bedside experience

### Idle state
- neutral face/status display, if the Bracket Bot includes a display;
- microphone off/not retaining audio except during an explicit interaction according to hospital policy;
- visible privacy indicator;
- large touch targets for “Ask for help”, “Room controls”, “What happens next?”, “Call staff”; 
- multilingual selection and captions;
- no advertising, engagement loops, or anthropomorphic claims that imply a clinician relationship.

### Conversational interaction
1. patient initiates by touch/wake interaction approved by hospital;
2. local/edge front-end captures only the interaction window;
3. deterministic request safety scan runs first;
4. request routes A/B/C/D;
5. UI says what will happen before doing it;
6. physical actions require object/policy confirmation and may require explicit patient/staff confirmation;
7. result is verified and stated plainly.

### Route A — information
UI shows:
- answer;
- source/system of record;
- last-updated time;
- clear “I don’t know yet” state;
- option to send a staff/service request.

### Route B — physical assistance
UI shows:
- recognized target (“your phone on the bedside table”);
- intended action;
- any required confirmation;
- safe cancel/stop control;
- completion verification.

### Route C — non-clinical human service
UI shows:
- where request was routed;
- current status if hospital system exposes it;
- no invented wait estimate.

### Route D — clinical/uncertain
UI shows only:
- “I’m contacting the appropriate staff now” (or exact hospital-approved wording);
- request status;
- emergency instructions defined by the hospital;
- no diagnostic interpretation.

## 2. Nurse / staff mobile surface

Primary screen is a prioritized exception queue:
- patient requests requiring human response;
- room-readiness failures;
- robot-blocked tasks with reason;
- asset search results;
- stale room-world-model warnings;
- robot faults and low battery.

Each card should answer four questions:
1. What happened?
2. Why does it matter?
3. What did the robot already do?
4. What is the smallest human action needed?

Do not create a parallel clinical task-management system if the hospital already has one; integrate and deep-link.

## 3. Charge nurse / unit console

Views:
- rooms by desired state and compliance;
- unresolved patient request categories;
- robot fleet position/status;
- tasks completed vs escalated;
- staff minutes returned (measured, not assumed);
- room state freshness;
- safety rejects;
- opt-out/privacy state.

## 4. Robotics operations console

Views:
- hardware model hash and verification state;
- SDK/firmware version;
- joint/sensor telemetry;
- localization quality;
- camera calibration version;
- E-stop/watchdog status;
- current simulation replay;
- planned trajectory and clearance envelope;
- execution logs;
- model calls and structured outputs;
- safety-kernel decision trace.

The staff clinical UI must never expose this complexity unless needed for support.

## 5. Research studio

The internal research app combines:
- patient/staff evidence corpus;
- pain-point clustering;
- opportunity ranking;
- 50-hospital image corpus provenance/review;
- scene archetypes;
- simulator scenario generator;
- failure taxonomy;
- experiment results.

A feature proposal is promoted only when it links to:
- at least one evidence theme;
- a measurable operational metric;
- an embodied advantage;
- a safety classification;
- a simulation scenario;
- a human workflow owner.

## 6. Accessibility requirements

- WCAG-aligned web/mobile UI;
- large touch targets and high contrast;
- captions for all speech output;
- support for speech-impaired users through touch/text;
- adjustable speech rate/volume within policy;
- no reliance on color alone;
- simple-language mode;
- multilingual UI;
- qualified interpreter escalation for clinical communication where required;
- patient ability to disable nonessential robot interaction.

## 7. Core metrics displayed in product

Patient experience:
- time to acknowledgment;
- time to resolution by request category;
- percent of non-clinical requests robot-resolved;
- percent escalated;
- patient opt-out rate;
- post-interaction helpfulness/satisfaction where appropriate.

Staff impact:
- interruptions avoided;
- walking/search time avoided;
- room-readiness check time;
- escalations created by robot;
- false/irrelevant alerts;
- staff correction rate.

Robot quality:
- perception precision/recall by object/policy class;
- successful navigation rate;
- manipulation success rate on allowlisted objects;
- minimum clearance;
- sim-to-real error;
- unexpected contact rate (target zero);
- safety-stop frequency and cause;
- post-action verification pass rate.


## 8. VLA + teleoperation operations UX

The VLA is an internal execution mode, not a patient-facing concept. A patient should see only understandable states such as “I can do that,” “I need a staff member,” or “I’m not confident enough to move that safely.”

### Staff task card
For any manipulation task, staff can inspect:

- requested outcome;
- target object;
- execution mode: `deterministic`, `VLA`, `teleoperation`, or `human`;
- policy/skill version;
- room-state timestamp;
- person-clearance state;
- safety approval;
- live/last head and wrist-camera verification thumbnails;
- result: success / abstained / staff needed.

### Robotics console
Add:

- head / left-wrist / right-wrist camera panes;
- base, linear-stage, left/right arm and gripper telemetry;
- active skill-router decision;
- VLA policy ID/version and validated task classes;
- out-of-distribution / abstention state;
- action-horizon countdown;
- safety-supervisor clips/rejections;
- teleoperation takeover available only to authorized operators;
- current demonstration recording state.

### “Teach task” research mode
Authorized research operators can create a task template and record demonstrations via Meta Quest. Capture task name, goal text, allowed object classes, room/scenario, operator, success/failure and correction notes. Recording is permitted only in an approved mock/research environment unless a separate hospital governance pathway exists.

### Policy promotion UI
No learned policy moves directly from training to production. Research states:

`draft -> offline-evaluated -> simulator-evaluated -> lab-supervised -> approved-for-bounded-task -> retired`

Promotion requires attached evaluation evidence and safety sign-off.


## VLA and supervised-manipulation UX

The staff console must expose the autonomy state of every physical task rather than presenting all actions as equally autonomous. Each task card shows one of:

- **Deterministic** — validated classical skill;
- **VLA validated** — bounded learned policy inside its approved envelope;
- **VLA supervised** — policy may run only with an authorized operator watching;
- **Teleoperation required** — Meta Quest/operator control only;
- **Observe only** — robot may inspect but cannot act;
- **Blocked** — prohibited by patient/object/hospital policy.

For a VLA task, the UI should display the task goal, target object, policy/version, validated task envelope, whether a patient/person is inside the exclusion zone, and the reason for any abstention. Staff should be able to choose **Take over with Quest**, **Ask staff instead**, or **Cancel** when a policy abstains.

The research console adds a skill lifecycle view:

`Teleoperate -> Review episode -> Add to dataset -> Train -> Evaluate -> Sim regression -> Lab rollout -> Promote / Reject`

This keeps demonstration learning visible and auditable instead of hiding it behind a generic “AI mode.”
