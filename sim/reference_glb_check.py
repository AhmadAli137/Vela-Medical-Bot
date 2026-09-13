"""Audit visual body bindings and textured room geometry against current physics."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

from sim.reference_model import load_reference_model


def _read_glb(path):
    payload = Path(path).read_bytes()
    if len(payload) < 20:
        raise ValueError("Truncated GLB header")
    magic, version, total = struct.unpack_from("<4sII", payload)
    if magic != b"glTF" or version != 2 or total != len(payload):
        raise ValueError("Invalid GLB header")
    chunks, offset = [], 12
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise ValueError("Truncated GLB chunk header")
        size, kind = struct.unpack_from("<I4s", payload, offset)
        offset += 8
        if size % 4 or offset + size > len(payload):
            raise ValueError("Invalid GLB chunk bounds")
        chunks.append((kind, payload[offset:offset + size]))
        offset += size
    if not chunks or chunks[0][0] != b"JSON":
        raise ValueError("GLB is missing its JSON chunk")
    binaries = [value for kind, value in chunks if kind == b"BIN\x00"]
    if len(binaries) > 1:
        raise ValueError("Multiple binary chunks")
    return json.loads(chunks[0][1]), binaries[0] if binaries else b"", hashlib.sha256(payload).hexdigest()


def _accessor(document, binary, index, expected_type):
    """Decode a bounded dense accessor, respecting component type and byte stride."""
    accessor = document["accessors"][index]
    if accessor.get("type") != expected_type or "sparse" in accessor:
        raise ValueError(f"Accessor {index} is not a supported dense {expected_type}")
    dtype = np.dtype({5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}[accessor["componentType"]])
    width, count = {"VEC2": 2, "VEC3": 3}[expected_type], accessor["count"]
    view = document["bufferViews"][accessor["bufferView"]]
    if view.get("buffer", 0) != 0 or document["buffers"][0].get("uri"):
        raise ValueError("Only the embedded GLB buffer is supported")
    start, length = view.get("byteOffset", 0), view["byteLength"]
    relative, item_size = accessor.get("byteOffset", 0), width * dtype.itemsize
    stride = view.get("byteStride", item_size)
    if (count < 1 or min(start, length, relative) < 0 or stride < item_size or stride % dtype.itemsize
            or start + length > min(len(binary), document["buffers"][0]["byteLength"])
            or relative + (count - 1) * stride + item_size > length):
        raise ValueError(f"Accessor {index} exceeds its binary buffer bounds")
    values = np.ndarray((count, width), dtype=dtype, buffer=binary,
                        offset=start + relative, strides=(stride, dtype.itemsize)).astype(float)
    if accessor.get("normalized") and dtype.kind in "iu":
        values /= np.iinfo(dtype).max
        if dtype.kind == "i":
            values = np.maximum(values, -1)
    if not np.isfinite(values).all():
        raise ValueError(f"Accessor {index} contains non-finite values")
    for key in ("min", "max"):
        if key in accessor and (len(accessor[key]) != width or not np.isfinite(accessor[key]).all()):
            raise ValueError(f"Accessor {index} has invalid declared {key} bounds")
    return values


def _texture_coordinates(material):
    result = set()
    for key, value in material.items():
        if not isinstance(value, dict):
            continue
        if key.endswith("Texture") and "index" in value:
            transform = value.get("extensions", {}).get("KHR_texture_transform", {})
            result.add(transform.get("texCoord", value.get("texCoord", 0)))
        result.update(_texture_coordinates(value))
    return result


def _check_poses(path, descriptors, model, data, all_names):
    report = {"file": str(path), "body_count": 0, "expected_body_count": len(descriptors), "bodies": [], "failures": []}
    failures = report["failures"]
    try:
        document, _, report["sha256"] = _read_glb(path)
        nodes = document.get("nodes", [])
        report["node_count"] = len(nodes)
        by_name = {}
        for index, node in enumerate(nodes):
            by_name.setdefault(node.get("name"), []).append(index)
        roots = set(document["scenes"][document.get("scene", 0)].get("nodes", []))
        parents = {child for node in nodes for child in node.get("children", [])}
        for name in all_names - {item["name"] for item in descriptors}:
            if name in by_name:
                failures.append(f"Unexpected physics body in this asset: {name}")
        for descriptor in descriptors:
            name = descriptor["name"]
            indices = by_name.get(name, [])
            if len(indices) != 1:
                failures.append(f"Expected exactly one body node for {name}; found {len(indices)}")
                continue
            index, = indices
            node = nodes[index]
            if index in parents or index not in roots:
                failures.append(f"Body {name} must be an active scene root with flattened world pose")
            if "matrix" in node:
                failures.append(f"Body {name} exports a matrix instead of a decomposed pose")
            scale = np.asarray(node.get("scale", [1, 1, 1]), dtype=float)
            position = np.asarray(node.get("translation", [0, 0, 0]), dtype=float)
            xyzw = np.asarray(node.get("rotation", [0, 0, 0, 1]), dtype=float)
            if (scale.shape != (3,) or position.shape != (3,) or xyzw.shape != (4,)
                    or not all(np.isfinite(value).all() for value in (scale, position, xyzw))):
                failures.append(f"Body {name} has invalid/non-finite pose components")
                continue
            if not np.allclose(scale, 1, atol=2e-5, rtol=0):
                failures.append(f"Body {name} has non-unit scale")
            physics_id = model.body(name).id
            quaternion, expected_q = xyzw[[3, 0, 1, 2]], data.xquat[physics_id]
            position_error = float(np.linalg.norm(position - data.xpos[physics_id]))
            quaternion_error = float(min(np.linalg.norm(quaternion - expected_q), np.linalg.norm(quaternion + expected_q)))
            if position_error > 2e-5 or quaternion_error > 2e-5:
                failures.append(f"Pose mismatch against current physics: {name}")
            visual_children = sum("mesh" in nodes[child] for child in node.get("children", []))
            if not visual_children:
                failures.append(f"Body {name} has no direct local visual child meshes")
            report["bodies"].append({"body": name, "position_error_m": position_error,
                                      "quaternion_error": quaternion_error, "visual_children": visual_children})
        report["body_count"] = len(report["bodies"])
    except (OSError, ValueError, KeyError, IndexError, TypeError, struct.error) as error:
        failures.append(f"Asset could not be validated: {error}")
    report["matched"] = not failures
    return report


def _check_room(path, dynamic_names):
    report = {"file": str(path), "textured_primitives": [], "failures": []}
    failures = report["failures"]
    try:
        document, binary, report["sha256"] = _read_glb(path)
        names = [item.get("name", "") for key in ("nodes", "meshes") for item in document.get(key, [])]
        duplicated = [name for name in names if any(body.lower() in name.lower() for body in dynamic_names)]
        report["dynamic_object_nodes_or_meshes"] = duplicated
        if duplicated:
            failures.append("Dynamic object names remain in static room nodes/meshes: " + ", ".join(duplicated))
        for mesh_index, mesh in enumerate(document.get("meshes", [])):
            for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
                if "material" not in primitive:
                    continue
                material = document["materials"][primitive["material"]]
                coordinate_sets = _texture_coordinates(material)
                if not coordinate_sets:
                    continue
                label = f"mesh {mesh_index} primitive {primitive_index} ({material.get('name', 'unnamed')})"
                try:
                    attributes = primitive["attributes"]
                    positions = _accessor(document, binary, attributes["POSITION"], "VEC3")
                    coordinates = []
                    for coordinate in sorted(coordinate_sets | {0}):
                        semantic = f"TEXCOORD_{coordinate}"
                        if semantic not in attributes:
                            raise ValueError(f"Missing {semantic}")
                        values = _accessor(document, binary, attributes[semantic], "VEC2")
                        if len(values) != len(positions):
                            raise ValueError(f"{semantic} count does not match POSITION")
                        coordinates.append({"semantic": semantic, "accessor": attributes[semantic], "count": len(values),
                                            "min": values.min(axis=0).tolist(), "max": values.max(axis=0).tolist(), "finite": True})
                    report["textured_primitives"].append({"mesh": mesh_index, "primitive": primitive_index,
                                                          "material": material.get("name"), "coordinates": coordinates})
                except (ValueError, KeyError, IndexError, TypeError) as error:
                    failures.append(f"{label}: {error}")
        report["textured_primitive_count"] = len(report["textured_primitives"])
    except (OSError, ValueError, KeyError, IndexError, TypeError, struct.error) as error:
        failures.append(f"Room asset could not be validated: {error}")
    report["matched"] = not failures
    return report


def check_glb(path="assets/simulation/robot.glb", *, phone_path=None, room_path=None):
    """Check all exports using fresh physics, never stale descriptor-file poses."""
    path = Path(path)
    model, data, metadata = load_reference_model()
    descriptors = metadata["body_specs"]
    dynamic = [item for item in descriptors if item.get("dynamic_object")]
    robot = [item for item in descriptors if not item.get("dynamic_object")]
    names = {item["name"] for item in descriptors}
    assets = [_check_poses(path, robot, model, data, names)]
    for descriptor in dynamic:
        dynamic_path = Path(phone_path) if phone_path and descriptor["name"] == "phone" else path.with_name(descriptor["name"] + ".glb")
        assets.append(_check_poses(dynamic_path, [descriptor], model, data, names))
    room = _check_room(Path(room_path) if room_path else path.with_name("room.glb"), {item["name"] for item in dynamic} | {"phone"})
    failures = [f"{asset['file']}: {failure}" for asset in [*assets, room] for failure in asset["failures"]]
    bodies = [body for asset in assets for body in asset["bodies"]]
    return {"file": str(path), "model_hash": metadata["model_hash"], "body_count": len(bodies), "expected_body_count": len(descriptors),
            "robot_body_count": assets[0]["body_count"], "dynamic_body_count": sum(asset["body_count"] for asset in assets[1:]),
            "matched": not failures, "failures": failures, "bodies": bodies, "assets": assets, "room": room,
            "hardware_model_verified": False, "authorizes_hardware": False,
            "limitations": ["Node-name checks cannot identify unnamed duplicate geometry",
                            "Visual pose and UV checks do not establish contact, grasp or weld behavior"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="assets/simulation/robot.glb")
    parser.add_argument("--phone")
    parser.add_argument("--room")
    parser.add_argument("--output", default="sim/outputs/reference_glb_check.json")
    args = parser.parse_args()
    report = check_glb(args.path, phone_path=args.phone, room_path=args.room)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("matched", "body_count", "expected_body_count", "failures")}))
    raise SystemExit(0 if report["matched"] else 1)
