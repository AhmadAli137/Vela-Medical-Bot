# Implementation status for this workspace

Current entrypoints and synchronization are described in the [app guide](APP_GUIDE.md). The native viewer now uses the reference scene and shared local session when opened from the app; the original primitive model remains an explicitly labeled benchmark.

The workspace began empty. This implementation is independent of the earlier scaffold described in `sources/IMPLEMENTATION_STATUS.md`.

Working now: FastAPI/React application; four views; deterministic clinical-first requests; synthetic information/FHIR/RTLS adapters; SQLite temporal room snapshots and task/audit persistence; eight semantic templates; constrained candidate/critic schemas; hash-bound approval/validation; deterministic veto; logical mock execution and verification; actual surrogate MuJoCo generation/dynamics/IK/contact checks and rendering; correction episodes, review/export, tiny synthetic offline training/evaluation/policy registry; evidence and image acquisition pipelines; documentation and tests.

The new browser simulation entry is **http://127.0.0.1:8000/#simulation**. Its detailed Blender-authored room uses inspected official Stanford/UCLA room photographs as architectural references and nine CC0 Poly Haven texture maps. The supplied PDF and three videos were inspected to inform a reference robot with **27 robot bodies and 22 physical actuators**. Actual MuJoCo dynamics stream body poses to Three.js. Geometry, axes and control parameters are inferred, not vendor verified; the native MuJoCo viewer now imports the same detailed reference assets.

Latest reference-specific checks: **9 physics tests and 5 API tests passed in separate suites** (`tests/test_reference_sim.py`, `tests/test_reference_api.py`). Direct simulation outcomes and limitations are recorded in [reference_actuation.json](../sim/outputs/reference_actuation.json). Earlier baseline evidence records 148 passing Python tests, four passing Chrome tests, a production frontend build, three passing scripted software workflows, a 12-episode surrogate benchmark, and five synthetic learning episodes. These are separate runs, not a summed current-suite total; see `TESTING.md` and the actual output artifacts.

Visual assets can be rebuilt with Blender 5.1 on `PATH`:

```powershell
blender --background --factory-startup --python scripts/build_reference_visuals.py -- --render
```

Optional PDF inspection dependency: `uv pip install --python .venv/Scripts/python.exe pymupdf`. It is not required to view the built demo. Source and license records are in [REFERENCE_UPGRADE.md](REFERENCE_UPGRADE.md) and `assets/provenance/`.

Partial/unconfigured: real Bracket Bot and Quest transport; verified robot model/control limits; calibrated perception; full motion/grasp validation; real VLA training and competence; live hospital delivery/acknowledgments; paid model calls; institutional approvals; production privacy/security deployment. The research image target remains unmet: 9 candidate URL records from one hospital, zero corpus image files or training-approved images, 50 named seed targets. Two separately cached local architectural reference photos do not change those corpus counts and have no established training/redistribution permission.

No physical action, real staff contact, clinical approval, measured time savings, regulatory compliance, photorealism, surveyed digital-twin fidelity, successful grasp or hardware accuracy is claimed.
