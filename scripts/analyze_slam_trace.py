"""Summarize recorded browser vision samples; never feeds truth to the estimator."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics


def distribution(values: list[float]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "median": None, "p95": None, "maximum": None}
    return {
        "count": len(ordered),
        "median": statistics.median(ordered),
        "p95": ordered[math.ceil(len(ordered) * .95) - 1],
        "maximum": ordered[-1],
    }


def analyze(path: Path) -> dict:
    raw = path.read_bytes()
    report = json.loads(raw)
    # The checker records one pre-demo observation, then one observation for
    # every demo trace sample. Validate that relationship before partitioning.
    assert len(report["vision"]) == 1 + sum(len(d["trace"]) for d in report["demos"])
    result = {
        "source": path.as_posix(),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_passed": report["passed"],
        "source_started": report["started"],
        "source_finished": report["finished"],
        "method": {
            "partition": "One pre-demo sample excluded; subsequent samples align with each demo trace in order; frame counter reset verified.",
            "availability": "Fraction of sampled post-origin observations with a current verified tracking/relocalized pose; not every sensor frame is logged.",
            "error": "Euclidean translation difference from isolated evaluation ground truth, recomputed from pose; first reset-origin sample excluded.",
            "p95": "Nearest rank: sorted values[ceil(0.95*n)-1].",
            "loss_timing": "Consecutive sampled lost statuses bracketed by adjacent observations; simulation elapsed time, not exact frame-level onset/recovery.",
            "orientation": "No ground-truth orientation is present in this trace; orientation accuracy is not evaluated.",
        },
        "runs": [],
    }
    offset = 1
    for demo in report["demos"]:
        trace = demo["trace"]
        samples = report["vision"][offset:offset + len(trace)]
        start_index = offset
        offset += len(samples)
        assert samples[0]["frames"] == 1, "Expected a new map/reset for each demo"
        assert samples[0]["metrics"]["inliers"] == 0
        assert all(a["frames"] < b["frames"] for a, b in zip(samples, samples[1:]))
        assert all(a["elapsed_s"] <= b["elapsed_s"] for a, b in zip(trace, trace[1:]))
        errors, valid_indices, moving_errors = [], [], []
        for index, sample in enumerate(samples):
            metrics, evaluation = sample["metrics"], sample["evaluation"]
            pose = metrics.get("pose")
            if pose is None:
                assert evaluation["positionErrorM"] is None
                continue
            error = math.dist(pose["position"], evaluation["groundTruthPosition"])
            assert math.isclose(error, evaluation["positionErrorM"], abs_tol=1e-10)
            if index and metrics["status"] in ("tracking", "relocalized") and metrics["inliers"] > 0:
                errors.append(error)
                valid_indices.append(index)
                dt = trace[index]["elapsed_s"] - trace[index - 1]["elapsed_s"]
                displacement = math.dist(evaluation["groundTruthPosition"], samples[index - 1]["evaluation"]["groundTruthPosition"])
                if dt > 0 and displacement / dt > .01:
                    moving_errors.append(error)
        losses, index = [], 1
        while index < len(samples):
            if samples[index]["metrics"]["status"] != "lost":
                index += 1
                continue
            first = index
            while index + 1 < len(samples) and samples[index + 1]["metrics"]["status"] == "lost":
                index += 1
            last = index
            losses.append({
                "first_sample_index": first, "last_sample_index": last,
                "sample_count": last - first + 1,
                "first_observed_lost_s": trace[first]["elapsed_s"],
                "last_observed_lost_s": trace[last]["elapsed_s"],
                "observed_lost_span_s": trace[last]["elapsed_s"] - trace[first]["elapsed_s"],
                "previous_observation_s": trace[first - 1]["elapsed_s"],
                "next_observation_s": trace[last + 1]["elapsed_s"] if last + 1 < len(samples) else None,
                "relocalizations_during_lost_samples": samples[last]["metrics"]["relocalizations"] - samples[first]["metrics"]["relocalizations"],
            })
            index += 1
        unseen_recoveries = []
        for index in range(1, len(samples)):
            previous, current = samples[index - 1]["metrics"], samples[index]["metrics"]
            change = current["relocalizations"] - previous["relocalizations"]
            if change and previous["status"] != "lost":
                unseen_recoveries.append({"between_samples": [index - 1, index], "between_elapsed_s": [trace[index - 1]["elapsed_s"], trace[index]["elapsed_s"]], "recovery_count": change})
        worst_index = max(valid_indices, key=lambda i: samples[i]["evaluation"]["positionErrorM"]) if valid_indices else None
        result["runs"].append({
            "command": demo["command"], "source_vision_start_index": start_index,
            "sample_count": len(samples), "origin_samples_excluded": 1,
            "sensor_frame_counter_final": samples[-1]["frames"],
            "sampled_status_counts": dict(Counter(s["metrics"]["status"] for s in samples)),
            "verified_temporal_samples": len(valid_indices), "post_origin_samples": len(samples) - 1,
            "sampled_temporal_availability": len(valid_indices) / (len(samples) - 1),
            "translation_error_m": distribution(errors),
            "camera_translating_error_m": distribution(moving_errors),
            "camera_translating_definition": "Consecutive ground-truth translation / demo elapsed interval exceeds 0.01 m/s; evaluation subset only.",
            "maximum_ground_truth_displacement_m": max(math.dist(s["evaluation"]["groundTruthPosition"], [0, 0, 0]) for s in samples),
            "maximum_map_size": max(s["metrics"]["mapSize"] for s in samples),
            "relocalizations": max(s["metrics"]["relocalizations"] for s in samples),
            "sampled_lost_intervals": losses, "recovery_between_polls_without_sampled_loss": unseen_recoveries,
            "processing_ms": distribution([s["metrics"]["processingMs"] for s in samples]),
            "worst_valid_pose_sample": None if worst_index is None else {"index": worst_index, "elapsed_s": trace[worst_index]["elapsed_s"], **samples[worst_index]},
        })
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = analyze(args.source)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for run in summary["runs"]:
        error = run["translation_error_m"]
        print(f"{run['command']}: {run['verified_temporal_samples']}/{run['post_origin_samples']} sampled temporal poses, "
              f"median/p95/max {error['median'] * 1000:.2f}/{error['p95'] * 1000:.2f}/{error['maximum'] * 1000:.2f} mm")
