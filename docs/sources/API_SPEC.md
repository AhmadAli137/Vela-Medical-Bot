# Application API specification

## Patient-facing boundary

### `POST /patient/requests/triage`
Accepts a patient request and returns Route A/B/C/D. Deterministic clinical/urgent triggers can force Route D; an AI classifier may never downgrade that result.

### Planned production endpoint: `POST /patient/requests/{id}/resolve`
Route A: retrieve authoritative operational answer. Route B: create a safety-gated robot task. Route C: route to service queue. Route D: initiate approved staff/clinical escalation.

## Room-state API

- `GET /rooms/{room_id}/state`
- `POST /rooms/{room_id}/snapshot`
- `POST /rooms/{room_id}/desired-state`
- `GET /rooms/{room_id}/desired-state/{state_name}/check`

Production adds version/history endpoints so a room can be diffed over time.

## Robot/fleet API

- `GET /robots/{robot_id}/capabilities`
- planned: heartbeat, battery, faults, localization quality, sensor calibration, E-stop/watchdog, current task, live model hash.

## Task lifecycle

1. `POST /tasks/plan`
2. independent model critique when enabled;
3. `POST /tasks/{id}/approve` when approval is required;
4. `POST /sim/validate-plan/{id}`;
5. deterministic safety decision;
6. `POST /tasks/{id}/execute` only when all gates pass;
7. post-action observation + verification;
8. immutable event log.

## Research endpoints

- `GET /research/opportunities` returns evidence-ranked pain points from the research corpus.

## Production services not mocked in this scaffold

- authentication/SSO/RBAC;
- hospital authoritative-status adapter;
- call-bell/nurse-call integration;
- RTLS/asset-management integration;
- EHR/FHIR integration under hospital governance;
- event streaming/audit storage;
- encrypted media gateway;
- device/fleet management;
- metrics/observability;
- clinical escalation integration;
- consent/preference service;
- multilingual qualified-interpreter workflow.


## VLA / demonstration-learning API (planned)

### Skill router
- `POST /skills/route` selects deterministic skill, approved VLA policy, teleoperation, or human escalation.
- Response includes task-policy match, reason, safety preconditions and approved execution envelope.

### Teleoperation data collection
- `POST /teleop/sessions`
- `POST /teleop/sessions/{id}/start`
- `POST /teleop/sessions/{id}/stop`
- `POST /teleop/sessions/{id}/label`
- `GET /teleop/sessions/{id}/manifest`

A session manifest references synchronized head stereo/depth, both wrist cameras, base pose, linear-stage state, both arms/grippers, operator actions and safety events. Raw media access is governed separately.

### VLA policy lifecycle
- `POST /vla/policies/register`
- `POST /vla/policies/{id}/evaluate`
- `POST /vla/policies/{id}/promote`
- `POST /vla/policies/{id}/retire`
- `GET /vla/policies/{id}`

A policy is scoped to explicit task classes and environment constraints. Promotion to hardware requires simulator/lab evidence and cannot bypass the deterministic safety service.

### VLA execution boundary
- `POST /vla/tasks/{task_id}/propose` may request a bounded policy rollout.
- The VLA service never exposes raw actuator endpoints externally.
- Every rollout receives a maximum duration/action horizon and can be interrupted by the safety supervisor, watchdog, E-stop or authorized teleoperator.


## VLA / teleoperation endpoints (application contract)

These are application-layer contracts; exact Bracket Bot SDK calls remain vendor-dependent.

- `GET /robots/{id}/skills` — deterministic and learned skills with validation status.
- `POST /robots/{id}/skills/{skill_id}/plan` — bind goal, object and constraints without execution.
- `POST /robots/{id}/skills/{skill_id}/execute` — execute only after deterministic policy approval.
- `POST /robots/{id}/teleop/session` — request authorized Meta Quest teleoperation.
- `POST /robots/{id}/teleop/session/{session_id}/record` — start/stop a demonstration episode.
- `GET /policies` — versioned VLA policies, task classes, validation envelopes and rollout metrics.
- `POST /policies/{policy_id}/evaluate` — run offline/simulation evaluation.
- `POST /policies/{policy_id}/promote` — guarded promotion requiring explicit validation evidence.

A VLA execution request must include a bounded task horizon and a deterministic constraint bundle (allowed object class, keep-out zones, max base/arm motion, patient/person clearance, payload envelope, timeout and stop conditions).
