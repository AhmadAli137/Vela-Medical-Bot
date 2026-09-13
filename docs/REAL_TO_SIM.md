# Real images to uncertain simulation hypotheses

The implemented boundary takes a reviewed semantic annotation and generates several **synthetic room priors**. It does not reconstruct metric 3D from a hospital photograph. The annotation's source, inventory and relationships remain in each output's metadata; the current room builder uses a fixed proxy asset catalogue and does not recreate every annotated object.

`sim.hypotheses.generate_hypotheses(annotation, output_dir, count=5, seed=31)` requires privacy review, analysis-rights review, source ID and source URL. It samples table height, clutter, starting base position, object mass/friction and a deterministic scene seed. At least two hypotheses are required. This prevents a single generated room from being presented as ground-truth geometry.

```python
from sim.hypotheses import generate_hypotheses

annotation = {
    "source_id": "synthetic-example-001",
    "source_url": "synthetic://example-not-an-acquired-photo",
    "privacy_reviewed": True,
    "rights_reviewed": True,
    "objects": [{"class": "bed"}, {"class": "bedside_table"}],
    "relationships": [{"subject": "bedside_table", "predicate": "beside", "object": "bed"}],
    "table_height_prior_m": [0.65, 0.9]
}
generate_hypotheses(annotation, "data/runtime/hypotheses", count=5)
```

The height prior above is an explicitly synthetic engineering assumption. A human or a separately configured structured scene adapter must supply actual reviewed annotations; this function does not imply that a model analyzed the example image. Each scene is loadable MJCF with provenance JSON and `hardware_model_verified=false`.

Runtime sensor reconstruction is a different boundary: calibrated depth, camera extrinsics, localization, synchronized timestamps and conservative occupancy geometry are required before a live robot path can be checked. The current application world model is synthetic. `validate_plan` samples object motion against that semantic state and checks simulator availability; it does not replace a full robot swept-volume planner or live perception.

Exact masses, friction, attachment state, patient safety, hinge torque and payload capacity cannot be read from a web photo. Camera streams from patient rooms are excluded from automatic training. The image acquisition/review pipeline retains its own provenance and licensing controls; reviewed analysis rights do not imply training or redistribution rights.

Next engineering steps are to map annotated assets into explicit geometry hypotheses, incorporate calibrated depth where available, support conservative unknown-space occupancy, propagate pose uncertainty through complete robot trajectories and compare predictions with independent post-action observations. These are material gaps, not completed capabilities.
