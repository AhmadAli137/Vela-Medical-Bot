# Hospital skill research matrix

The arm topology and supplied teleoperation summaries motivate these benchmarks. They do not demonstrate autonomous execution or grant permission in a hospital. All real patient contact, patient support/repositioning, medication/sharps, attached lines/tubes, clinical controls and alarms remain prohibited irrespective of policy competence.

| Benchmark | Task and intended value | Variables to evaluate | Current implementation and limits |
|---|---|---|---|
| A | Cluttered phone/glasses/remote retrieval; personal-item independence | Object instance/pose, occlusion, lighting, table height, approach, clutter | Randomized rigid props and endpoint IK; synthetic feature-BC pipeline. No physics grasp or visual retrieval success demonstrated. |
| B | Approved drawer/handle family | Handle geometry, articulation, friction, partial open state, failed first contact | Loadable sliding drawer and handle proxy. No autonomous handle skill or benchmark completion result. |
| C | Bimanual clean bag stabilization | Bag pose, load distribution, coordinated grasp, one-arm recovery | Both arms move under actual MuJoCo servo dynamics; bag is a rigid proxy. No bimanual manipulation competence. |
| D | Clean fabric on empty surface | Deformation, fold state, visibility, tension, support surface | Registry/research definition only. Cloth is not simulated. Requires real teleop demonstration and supervised lab validation. |
| E | Restore allowlisted room objects to semantic state | 3-5 object placements, egress, target zones, unavailable items | Application semantic planning/diff and logical mock moves; swept-object/person-zone checks. No physical chair/table moving claim. |
| F | Abstain for unsafe or unknown requests | Prohibited/unknown object, uncertain identity, load, attached object, poor grasp, person proximity, blocked path, OOD | Executed deterministic fixture suite with explicit reasons. Not learned abstention or a certified hospital safety threshold. |

Every experimental task should retain success, first-attempt success, correction/intervention, elapsed time, contact/drop rates, minimum clearance, unsafe attempts, OOD/abstention quality and independent post-action verification. Store unknown rates as null. The current reports intentionally leave task, grasp, bimanual and sim-to-real outcomes null.

Progression is task-specific: approved mock-room teleoperation, reviewed synchronized dataset, heldout offline evaluation, surrogate/software regression, vendor model validation, supervised lab trials, repeated safety/effectiveness review and then a separately authorized bounded pilot. A policy can add capability without adding authority.
