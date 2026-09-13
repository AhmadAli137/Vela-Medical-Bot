"""Generate uncertain room priors from reviewed semantic annotations.

This module takes an annotation produced by a human or optional structured scene
adapter. It never calls an image a metric scan and never downloads image content.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim.model import write_scene


def generate_hypotheses(annotation: dict, output_dir: str | Path, count=5, seed=31):
    if not 2 <= count <= 50:
        raise ValueError("A monocular annotation requires 2-50 plausible scene hypotheses")
    if annotation.get("privacy_reviewed") is not True or annotation.get("rights_reviewed") is not True:
        raise ValueError("Scene-prior generation requires explicit privacy and analysis-rights review")
    if not annotation.get("source_url") or not annotation.get("source_id"):
        raise ValueError("Annotation needs source ID and provenance URL")
    inventory = annotation.get("objects", [])
    if not inventory:
        raise ValueError("A reviewed semantic object inventory is required")
    rng = np.random.default_rng(seed)
    output_dir = Path(output_dir)
    manifests = []
    height_range = annotation.get("table_height_prior_m", [.65, .9])
    if not isinstance(height_range, list) or len(height_range) != 2 or not .45 <= height_range[0] < height_range[1] <= 1.1:
        raise ValueError("Use a bounded uncertain table-height prior; never a precise photo-derived claim")
    for i in range(count):
        metadata = write_scene(output_dir / f"hypothesis_{i:03}", seed+i, clutter=int(rng.integers(1, 7)), robot_xy=(float(rng.uniform(-.15, .15)), float(rng.uniform(-.15, .15))), table_height=float(rng.uniform(*height_range)))
        metadata.update(source_id=annotation["source_id"], source_url=annotation["source_url"], annotation_objects=inventory, relationships=annotation.get("relationships", []), uncertainty={"metric_reconstruction": False, "physics_from_photo": False, "geometry_source": "parametric synthetic room fixture", "inventory_mapping": "annotation preserved as provenance; fixed proxy asset catalogue, not per-object reconstruction", "table_height_prior_m": height_range}, authorizes_hardware=False)
        (output_dir / f"hypothesis_{i:03}" / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        manifests.append(metadata)
    report = {"source_id": annotation["source_id"], "hypotheses": manifests, "count": count, "hardware_model_verified": False, "single_image_is_not_metric_ground_truth": True}
    (output_dir / "hypotheses.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
