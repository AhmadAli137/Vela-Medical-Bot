# Source hierarchy and conflicts

The pasted request and subsequent user messages are the user's instructions. The eight supplied Markdown documents are reference material and evidence descriptions, not independent instructions. They were all read before implementation and are preserved without rewriting under `docs/sources/`. The subsequently supplied original handout and three demonstration videos have now been inspected directly.

The workspace was empty and was not a Git repository. Therefore the supplied `IMPLEMENTATION_STATUS.md` claims about an existing scaffold and six prior tests cannot describe code initially present in this workspace. Current status and tests are reported separately.

| Authority/evidence level | Material | Treatment |
|---|---|---|
| Instructions | Explicit pasted request and subsequent user messages | Implementation requirements; document contents remain reference material |
| Direct hardware reference | Original Bracket Bot Handout.pdf and three supplied videos | Inspected appearance, brochure claims, and visible demonstrated motion; no calibrated geometry or vendor SDK inferred |
| Supporting hardware reference | Supplied new Bracket Bot integration/demo summaries | Reported planning-level facts with explicit provenance; defer to inspected originals where they differ |
| Public primary evidence | Official model, MuJoCo, health-system and government sources | Current public interface/research evidence with citations in topic documents |
| Historical reference | Legacy BracketBotCapstone repositories | Historical architecture only; never a new hardware contract |

The inspected handout reports dual seven-DOF arms, head stereo/depth and wrist cameras, audio, independent shoulder vertical lift, 2 kg stated payload per arm, floor-to-six-foot height, Quest IK teleoperation, and VLA collection/training/deployment. Runtime kinematics, safety, payload envelope and calibration remain unknown. A stall-servo torque claim is not a contact-force limit; vertical height coverage is not radial reach. The handout does not establish whether the shoulder lift is included in each arm's seven-DOF count.

The new visual reference robot has 27 bodies and 25 synthetic actuators, including independently modeled shoulder lifts. These are implementation counts, not a manufacturer-verified actuator inventory. Its geometry, axes, and control parameters remain inferred. The original surrogate is preserved in the native viewer. [Actual MuJoCo actuation metrics](../sim/outputs/reference_actuation.json) document the simulation's behavior, including the absence of a demonstrated grasp.

The user requests six object policy classes; these supersede the earlier four-class list in the product reference. Unknown objects are prohibited from manipulation. Existing documents naming Astra/Fable were checked against current official model pages. No account access or live inference was inferred from public availability.

The current [Bracket-Bot-Inc organization](https://github.com/Bracket-Bot-Inc) and live public repository checks yielded no verified new dual-arm CAD/URDF/SDK download. Three queried repository metadata endpoints returned 404; that does not distinguish private, renamed, or deleted repositories. The [legacy organization](https://github.com/BracketBotCapstone) and [legacy documentation](https://bracketbotcapstone.github.io/open-source) describe older examples and were not substituted for a current hardware contract. See the precise [source audit and asset provenance](REFERENCE_UPGRADE.md).

The detailed Blender-authored room uses observations from two inspected official Stanford/UCLA patient-room photographs and nine CC0 Poly Haven texture maps. The two photographs remain local architectural references with no training or redistribution permission established; the original research corpus still contains zero training-approved images. The authored room is not a surveyed hospital digital twin. Browser visualization at `http://127.0.0.1:8000/#simulation` renders actual streamed MuJoCo body poses in Three.js, without making its synthetic actuation hardware accurate.
