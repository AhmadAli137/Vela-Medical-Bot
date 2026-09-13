# Prototype safety case

Claim supported by this implementation: untrusted natural-language candidates cannot directly issue physical motor commands, and synthetic task execution is subject to deterministic, auditable vetoes. This is a software research claim, not certification or a hospital-approved safety case.

| Hazard | Implemented control | Remaining requirement |
|---|---|---|
| Clinical request downgraded | Unicode-normalized critical rules precede classification; risk only escalates | Clinical vocabulary, language and adversarial validation with hospital owners |
| Clinical/unknown object moved | Semantic class, sensitivity and object permission independently veto | Validated perception, attachments and instance identity |
| Stale approved action | Full room hash/version, plan hash and policy version binding; freshness timeout | Synchronized perception and bounded live control latencies |
| Person enters path | Synthetic segment-distance and conservative keep-out checks | Reliable dynamic person detection; full swept robot volume and protective stops |
| Unsafe learned action | Training-data review, artifact hash, distribution/horizon/delta checks; no direct actuation | Actual VLA action interface and live task-specific envelope |
| False completion | Reobserve mock state and verify semantic predicates; full desired-state check for templates | Independent multi-view physical grasp/placement verification |
| Simulation mistaken for vendor proof | Every report `hardware_model_verified=false`, `authorizes_hardware=false`; unconditional vendor refusal | Verified CAD, calibration, real/sim comparisons |
| E-stop bypass | Software flag veto and approval invalidation on state changes | Physical independent E-stop/watchdog; current flag is not a hardware primitive |
| Consent bypass into training | Operational/training separation; recording consent; quarantined episodes; explicit review/export | Institutional consent, privacy/redaction assurance, retention and audit systems |

The policy is implemented separately from model adapters but is in the same Python process. Process failure, network delay, missing detections or compromised host are not solved by this software. Production requires vendor-level stopping primitives and a physically independent safety architecture.

All payload, clearance, joint, velocity and observation thresholds in the surrogate are research fixture parameters. They must not be used as limits on an actual Bracket Bot. Task path checks omit full grasp, swept-arm, contact-force, stability and payload validation. The clinical lexical router is conservative but finite and unvalidated; missed phrasing is possible.

Permitted classes are SAFE_GENERAL, SAFE_WITH_POLICY, STAFF_APPROVAL, TELEOP_ONLY, CLINICAL_PROHIBITED and UNKNOWN_PROHIBITED. Staff approval does not override clinical prohibition. UI policy updates may narrow permission only. Unknown objects, attachments, confidence and mass fail closed. Production code paths for physical actuation do not exist.

The safety tests include negated/combined clinical requests, prohibited-object relabeling, stale scans, malformed schemas, missing limits, E-stop release, person entry, attached objects, unreviewed datasets, artifact tampering and concurrent task execution. See [TESTING](TESTING.md) for actual command/results.

