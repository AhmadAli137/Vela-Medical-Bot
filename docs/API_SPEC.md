# Implemented API

Current reference simulation: `GET /api/sim/reference/state` and `POST /api/sim/reference/control` serve the local 3D session. `GET /api/sim/reference/frame` returns one coherent read-only state plus qpos/qvel/ctrl/mocap arrays for the attached native viewer. It has the same demo-mode/session/role boundary; there is no frame-write endpoint. `POST /api/sim/viewer` opens that attached desktop view, and `GET /api/sim/scene.png` renders the current detailed reference fixture with asset-sensitive cache invalidation. `POST /api/sim/benchmarks` retains the explicitly labeled legacy benchmark. See [the app guide](APP_GUIDE.md).

Interactive specification: `/docs`; machine-readable specification: `/openapi.json`. A generated copy is checked in at [openapi.json](openapi.json). All application routes use `/api`. The supplied reference described aspirational routes; only endpoints in the generated contract are implemented.

The interactive documentation loads standard Swagger UI assets from jsDelivr and needs network access. The operational application, bundled fonts and raw OpenAPI JSON work locally. Only documentation pages have this CDN content-policy exception.

| Area | Routes | Authority |
|---|---|---|
| Session | `POST/DELETE /api/session`, `GET /api/health` | Loopback role switch or configured role token |
| Workspace | `GET /api/bootstrap` | Authenticated; patient tasks scoped to session |
| Requests | `POST /api/requests`, `/api/requests/triage` | Authenticated; deterministic clinical priority |
| Room | `GET /api/rooms/{id}/state`, `/diff`, `/history`; `POST /scan`, `/snapshot` | Staff/operator changes, patient room-only read |
| Object policy | `POST /api/rooms/{id}/objects/{object_id}/policy` | Staff may restrict, never relax clinical policy |
| Tasks | `POST /api/tasks/plan`; `GET /api/tasks/{id}`; `POST /approve`, `/validate`, `/execute`, `/cancel` | Staff approval; staff/operator execution; own-session patient cancel |
| Fleet | `GET /api/robots/{id}/capabilities`; `POST /estop` | Staff/operator; software stop only |
| Privacy | `POST /api/privacy` | Authenticated bedside preferences; no raw retention |
| Teleop | `POST /api/teleop/sessions`; `POST /{id}/frames`, `/demo-correction`, `/complete`, `/review` | Operator recording, researcher review |
| Learning | `GET /api/policies`; `POST /register`, `/train`, `/{id}/evaluate`, `/promote`, `/retire`, `/rollback` | Research; physical promotion denied |
| Export | `POST /api/datasets/export` | Reviewed episodes + explicit export approval |
| Skill router | `POST /api/skills/route` | Operator/research; proposal only |
| Simulation | `POST /api/sim/benchmarks`, `/viewer`; `GET /reports/{id}`, `/scene.png` | Bounded episodes, actual surrogate diagnostics; native viewer restricted to local demo |
| Research | `GET /api/research` | Staff/operator/research |
| Audit | `GET /api/audit` | Operator/admin |
| Failure fixtures | `POST /api/demo/scenario` | Operator/admin; synthetic only |

Mutations validate roles and request origins. Session cookies are HttpOnly, SameSite Strict, one-hour lifetime; Secure outside local demo mode. Input models reject extra planner/request fields and nonfinite numeric schema values. Unknown IDs return 404, invalid lifecycle transitions 409, missing authorization 401/403, and schema failures 422.

Task sequence: plan → approve and validate (either order) → execute → verified completion. Approval binds to the plan hash; plan and simulation bind to the complete room hash/version. A scan, privacy change or policy change invalidates a previous plan. Execution returns a task with `status=blocked` and an explicit safety trace if vetoed. Repeated execution of completed tasks is rejected. Hardware target requests are always vetoed.

`POST /api/teleop/sessions/{id}/demo-correction` records 12 synthetic frames containing state/action values and opaque `synthetic://` references, not camera pixels. It does not complete a physical task. Reviewed data export and policy activation require separate explicit research signoff.
