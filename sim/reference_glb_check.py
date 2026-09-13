"""Verify exported robot body nodes match the physics pose contract."""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np

from sim.reference_model import load_reference_model


def check_glb(path):
    payload = Path(path).read_bytes()
    magic, version, total = struct.unpack_from("<4sII", payload)
    if magic != b"glTF" or version != 2 or total != len(payload):
        raise ValueError("Invalid GLB header")
    size, chunk_type = struct.unpack_from("<I4s", payload, 12)
    if chunk_type != b"JSON":
        raise ValueError("GLB is missing its JSON chunk")
    document = json.loads(payload[20:20+size])
    nodes = document.get("nodes", [])
    by_name = {node.get("name"): index for index, node in enumerate(nodes)}
    parents = {child: index for index, node in enumerate(nodes) for child in node.get("children", [])}
    model, data, metadata = load_reference_model()
    reports, failures = [], []
    for descriptor in metadata["body_specs"]:
        name = descriptor["name"]
        if name not in by_name:
            failures.append(f"Missing body node: {name}")
            continue
        index = by_name[name]
        node = nodes[index]
        if index in parents:
            parent_name = nodes[parents[index]].get("name")
            if parent_name in {d["name"] for d in metadata["body_specs"]}:
                failures.append(f"Body {name} unexpectedly parented to another body {parent_name}; browser expects flattened world poses")
        expected_position = data.xpos[model.body(name).id]
        expected_q = data.xquat[model.body(name).id]
        quaternion_xyzw = node.get("rotation", [0, 0, 0, 1])
        quaternion = np.asarray([quaternion_xyzw[3], *quaternion_xyzw[:3]])
        position = np.asarray(node.get("translation", [0, 0, 0]))
        if "matrix" in node:
            failures.append(f"Body {name} exports a matrix instead of decomposed pose; inspect coordinate conversion")
        position_error = float(np.linalg.norm(position-expected_position))
        quaternion_error = float(min(np.linalg.norm(quaternion-expected_q), np.linalg.norm(quaternion+expected_q)))
        if position_error > 2e-5 or quaternion_error > 2e-5:
            failures.append(f"Pose mismatch: {name}")
        if not node.get("children"):
            failures.append(f"Body {name} has no local visual child meshes")
        reports.append({"body": name, "position_error_m": position_error, "quaternion_error": quaternion_error, "visual_children": len(node.get("children", []))})
    return {"file": str(path), "body_count": len(reports), "expected_body_count": len(metadata["body_specs"]), "node_count": len(nodes), "matched": not failures, "failures": failures, "bodies": reports, "hardware_model_verified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="assets/simulation/robot.glb")
    parser.add_argument("--output", default="sim/outputs/reference_glb_check.json")
    args = parser.parse_args()
    report = check_glb(args.path)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["matched"] else 1)
