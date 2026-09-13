# Known gaps and highest-risk assumptions

This pass delivers working local software, research tools and synthetic demonstrations. The browser demo at `http://127.0.0.1:8000/#simulation` now combines a detailed Blender-authored room, inspected hospital imagery as architectural reference, CC0 textures, and actual MuJoCo dynamics streamed to Three.js. The following remain incomplete.

| Boundary | Actual status | Replacement needed |
|---|---|---|
| Bracket Bot | Planning-level reported manifest; physical execution unconditionally disabled | Production SDK, exact model/limits, stop/watchdog, calibration and live handshake |
| Original hardware evidence | Eight summaries preserved; original PDF and three videos now inspected | Vendor-confirmed CAD/URDF, joint axes/limits, actuator inventory and runtime documentation |
| Perception | Synthetic semantic room; no real sensor fusion or object tracking | Calibrated multi-view RGB-D, localization, attachment/person detection |
| MuJoCo validation | Reference model has 27 bodies/25 synthetic actuators; real dynamics streamed into Three.js, with endpoint and contact diagnostics; original native surrogate retained | Vendor-verified kinematics/dynamics, full motion/grasp validation, real balancing and odometry; see [actual metrics](../sim/outputs/reference_actuation.json) |
| Visual fidelity | Detailed Blender-authored room informed by inspected Stanford/UCLA photographs and nine CC0 texture maps | Surveyed room geometry and calibrated appearance; no photorealism or digital-twin fidelity established |
| VLA | Registry, collection/review/export gates, actual tiny synthetic feature baseline | Real synchronized demos, image/language-conditioned training, vendor action schema and lab evaluations |
| Quest | Software ownership/recording workflow, no transport | Verified headset/vendor teleoperation integration and safe takeover handshake |
| Hospital | Synthetic information, FHIR-style tasks, RTLS unknowns | Institution-specific authentication, semantics, acknowledgments and failure escalation |
| Clinical routing | Conservative English lexical prototype; ambiguous requests escalate | Hospital-owned multilingual routing validation; approved emergency workflow |
| Privacy/security | Role checks, loopback demo, token mode, origin checks, no live patient-media ingestion, audit chain; supplied/reference media retained locally | SSO, encryption at rest, key management, immutable remote audit, legal/governance assessment |
| Datasets | 50 named seed targets; 9 candidate URLs from 1 hospital; zero corpus image files/training images/raw comments; 2 separate local architectural reference photos | Rights clearance, consent/privacy review, broader permissible collection; 1,000/50 target unmet; reference photos are not training-approved |
| Customer impact | Software counts/timings only; clinical and staff impact unmeasured | Co-designed usability tests and prospective pilot measures |
| Cloud providers | Current official API clients behind opt-in; synthetic input only | Credentials and live schema/refusal/network testing; no patient-data approval implied |

Five highest-risk technical assumptions:

1. A future vendor controller can expose sufficiently bounded, stoppable dual-arm/base/lift commands and synchronized observations.
2. Perception can reliably identify permitted instances, hidden attachments and people in cluttered rooms; the current synthetic oracle avoids that difficulty.
3. A surrogate's successful endpoint/dynamics checks will transfer to measured hardware; that transfer is currently untested and cannot authorize execution.
4. A trained VLA will generalize from reviewed demos to useful room tasks while abstaining outside its distribution; no such competence has been demonstrated.
5. Desired-state predicates and staff approval can express a useful hospital workflow without creating additional work or unsafe omission; no clinical workflow owner has validated them.

Five next priorities:

1. Obtain the current vendor SDK/model/calibration/safety contract; compare it with the now-inspected handout/videos and implement an authenticated observe-only handshake.
2. Qualify E-stop/watchdog and controller timing in a mock lab, then compare real telemetry against a measured MuJoCo model.
3. Collect consented synchronized Quest demonstrations for phone retrieval and explicit abstention; train a real VLA offline and evaluate novel instances.
4. Co-design object policies, call routing, privacy and room templates with patient advisers, nursing, infection prevention and hospital operations.
5. Secure image/data rights and expand the reviewed corpus; perform accessibility/usability testing and measure workflow value before a limited observational pilot.
