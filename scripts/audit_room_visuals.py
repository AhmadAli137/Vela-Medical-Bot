"""Check generated furniture support, surface connections and bedding gaps.

Blender, pre-merge scene:
  blender --background scene.blend --python scripts/audit_room_visuals.py -- --scene
Blender, build only room() without exports or rendering:
  blender --background --factory-startup --python scripts/audit_room_visuals.py -- --builder scripts/build_reference_visuals.py
Bounds-only inspection, also runnable with ordinary Python:
  python scripts/audit_room_visuals.py --manifest assets/simulation/room-geometry-manifest.json

The Blender mode uses evaluated world-space meshes and BVHs. A bounds manifest
can prove separations but cannot prove surface contact through hollow objects.
Neither mode certifies load capacity, furniture safety or clinical suitability.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ASSEMBLIES = {"hospital_bed", "visitor_chair", "wardrobe", "bedside_storage", "bedside_table", "visitor_table", "room_plant"}
PATIENT_SUPPORTS = {"patient_anatomical_skin", "patient_hospital_gown", "patient_contoured_blanket", "patient_blanket_turned_hem"}
# Semantic completeness of this furniture design, not authored coordinates.
REQUIRED_PARTS = {
    "hospital_bed": {"Bed caster tire": 4, "Bed support deck": 1, "Mattress core": 1,
                     "Fitted cotton sheet": 1, "Pillow loft": 1, "Bed end board": 2,
                     "Bed lift support": 2, "Rail support socket": 8, "Safety rail horizontal": 8},
    "visitor_chair": {"Visitor chair leg": 4, "Visitor chair seat": 1, "Visitor chair upholstered back": 1,
                      "Visitor chair padded arm": 2, "Visitor chair arm front post": 2, "Visitor chair back upright": 2},
    "wardrobe": {"Wardrobe carcass": 1, "Wardrobe door": 1, "Brushed handle": 1, "Wardrobe recessed plinth": 1},
    "bedside_storage": {"Bedside storage": 1, "Bedside storage top": 1, "Drawer face": 1, "Drawer pull": 1},
    "bedside_table": {"Bedside tabletop": 1, "Table aluminium leg": 4, "Table rubber foot": 4, "Raised phone pickup rest": 1},
    "visitor_table": {"Round visitor table top": 1, "Visitor table stem": 1, "Visitor table foot": 1,
                      "Water cup base": 1, "Open cup wall": 1, "Rolled cup rim": 1},
    "room_plant": {"Plant pot base": 1, "Plant pot open wall": 1, "Plant pot rounded rim": 1, "Plant soil": 1},
}


def semantic_name(name):
    return re.sub(r"\.\d+$", "", name)


def is_soft_layer(part):
    return part.name.startswith(("Fitted cotton", "Sage patient", "Turned blanket", "Pillow loft",
                                 "patient_contoured_blanket", "patient_blanket_turned_hem", "patient_hospital_gown"))


def infer_assembly(name):
    if name.startswith(("Bedside storage", "Drawer")):
        return "bedside_storage"
    if name.startswith(("Bedside tabletop", "Table ", "Raised phone", "Soft glasses")):
        return "bedside_table"
    if name.startswith(("Bed ", "Caster ", "Rail ", "Safety rail", "Mattress", "Fitted cotton", "Pillow", "Sage patient", "Turned blanket")):
        return "hospital_bed"
    if name.startswith("Visitor chair"):
        return "visitor_chair"
    if name.startswith(("Wardrobe", "Brushed handle")):
        return "wardrobe"
    if name.startswith(("Round visitor", "Visitor table", "Water cup")):
        return "visitor_table"
    if name.startswith(("Plant pot", "Plant soil")):
        return "room_plant"
    return None


@dataclass
class Part:
    name: str
    assembly: str
    low: list
    high: list
    material: str | None = None
    vertex_count: int = 0
    polygon_count: int = 0
    vertices: list = field(default_factory=list, repr=False)
    bvh: object = field(default=None, repr=False)

    def record(self):
        return {"name": self.name, "assembly": self.assembly, "min": self.low, "max": self.high,
                "material": self.material, "vertices": self.vertex_count, "polygons": self.polygon_count}


def _included(name, assembly):
    if name == "Floor slab":
        return True
    if semantic_name(name) in PATIENT_SUPPORTS:
        return True
    # Plant stems/leaves are decorative, not furniture load paths.
    return assembly in ASSEMBLIES and (assembly != "room_plant" or name.startswith(("Plant pot", "Plant soil")))


def collect_scene(objects=None):
    import bpy
    from mathutils.bvhtree import BVHTree

    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    parts = []
    for obj in objects if objects is not None else bpy.context.scene.objects:
        assembly = obj.get("assembly") or infer_assembly(obj.name)
        if obj.type != "MESH" or not _included(obj.name, assembly):
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            vertices = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
            if not vertices:
                continue
            polygons = [tuple(face.vertices) for face in mesh.polygons]
            low = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
            high = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
            bvh = BVHTree.FromPolygons(vertices, polygons, all_triangles=False, epsilon=1e-7)
            audit_assembly = "hospital_bed" if semantic_name(obj.name) in PATIENT_SUPPORTS else assembly
            parts.append(Part(obj.name, audit_assembly or "room_architecture", low, high,
                              obj.active_material.name if obj.active_material else None,
                              len(vertices), len(polygons), vertices, bvh))
        finally:
            evaluated.to_mesh_clear()
    return parts


def collect_manifest(path):
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if document.get("units", "m") not in ("m", "metres", "meters"):
        raise ValueError("The geometry manifest must use metres")
    parts = []
    for obj in document["objects"]:
        name = obj["name"]
        assembly = obj.get("assembly") or infer_assembly(name)
        if not _included(name, assembly):
            continue
        low, high = obj.get("min"), obj.get("max")
        if low is None or high is None:
            corners = obj["corners"]
            low = [min(corner[axis] for corner in corners) for axis in range(3)]
            high = [max(corner[axis] for corner in corners) for axis in range(3)]
        audit_assembly = "hospital_bed" if semantic_name(name) in PATIENT_SUPPORTS else assembly
        parts.append(Part(name, audit_assembly or "room_architecture", low, high, obj.get("material"),
                          obj.get("vertices", 0), obj.get("polygons", 0)))
    return parts


def bounds_gap(a, b):
    return math.sqrt(sum(max(0., a.low[i] - b.high[i], b.low[i] - a.high[i]) ** 2 for i in range(3)))


def _inside(point, tree):
    from mathutils import Vector

    direction = Vector((.829, .371, .417)).normalized()
    origin, hits = point.copy(), 0
    for _ in range(64):
        location, _, _, _ = tree.ray_cast(origin, direction, 100.)
        if location is None:
            return bool(hits % 2)
        hits += 1
        origin = location + direction * 1e-6
    return False


def surface_gap(a, b):
    """BVH intersection, containment, then sampled surface nearest distance."""
    if a.bvh is None or b.bvh is None:
        return bounds_gap(a, b)
    if a.bvh.overlap(b.bvh):
        return 0.
    for source, target in ((a, b), (b, a)):
        if bounds_gap(a, b) == 0:
            step = max(1, len(source.vertices) // 12)
            if any(_inside(point, target.bvh) for point in source.vertices[::step]):
                return 0.
    nearest = math.inf
    for source, target in ((a, b), (b, a)):
        # BVH overlap already covers intersecting surfaces. Sample up to 6000
        # vertices for nearest-distance checks on large human/cloth meshes.
        step = max(1, len(source.vertices) // 6000)
        for point in source.vertices[::step]:
            result = target.bvh.find_nearest(point)
            if result[0] is not None:
                nearest = min(nearest, result[3])
                if nearest < 1e-7:
                    return 0.
    return nearest


def _bedding_checks(parts, maximum_gap=.008, maximum_penetration=.008):
    from mathutils import Vector

    support_prefixes = {
        "Pillow loft": ("Fitted cotton sheet", "Mattress core"),
        "Sage patient blanket": ("Fitted cotton sheet", "Mattress core"),
        "Turned blanket hem": ("Sage patient blanket",),
        "patient_contoured_blanket": ("Fitted cotton sheet", "Mattress core", "patient_anatomical_skin", "patient_hospital_gown"),
        "patient_blanket_turned_hem": ("patient_contoured_blanket",),
    }
    checks = []
    for name, prefixes in support_prefixes.items():
        for source in [part for part in parts if part.name.startswith(name)]:
            supports = [part for part in parts if part.name.startswith(prefixes)]
            gaps = []
            samples = []
            draped = name == "patient_contoured_blanket"
            coordinates = tuple(.2 + .6 * index / 12 for index in range(13)) if draped else (.3, .5, .7)
            bridges = []
            for u in coordinates:
                for v in coordinates:
                    x = source.low[0] + u * (source.high[0] - source.low[0])
                    y = source.low[1] + v * (source.high[1] - source.low[1])
                    bottom = source.bvh.ray_cast(Vector((x, y, source.low[2] - 1)), Vector((0, 0, 1)), 3.)[0]
                    if bottom is None:
                        continue
                    tops = []
                    for part in supports:
                        hit = part.bvh.ray_cast(Vector((x, y, source.high[2] + 1)), Vector((0, 0, -1)), 3.)
                        if hit[0] is None:
                            continue
                        if draped and hit[0].z > bottom.z + maximum_penetration:
                            # Hands may rest above a blanket. Probe immediately
                            # above its underside to distinguish an overhead
                            # object from cloth penetrating a closed body.
                            below = part.bvh.ray_cast(Vector((x, y, bottom.z + maximum_penetration)), Vector((0, 0, -1)), 3.)
                            if below[0] is None:
                                continue
                            if below[1].z >= -.05:
                                hit = below
                        tops.append((part.name, hit[0].z))
                    if tops:
                        support_name, top_z = max(tops, key=lambda entry: entry[1])
                        measured_gap = float(bottom.z - top_z)
                        sample = {"xy": [x, y], "underside_z": float(bottom.z), "support": support_name,
                                  "support_z": float(top_z), "gap_m": measured_gap}
                        if draped and not support_name.startswith(("patient_anatomical_skin", "patient_hospital_gown")):
                            # A drape can bridge the space between or beside
                            # legs; mattress clearance there is not a cloth gap
                            # against an anatomical supporting surface.
                            bridges.append(sample)
                        else:
                            gaps.append(measured_gap)
                            samples.append(sample)
            median = sorted(gaps)[len(gaps) // 2] if gaps else None
            # Nine footprint samples spread over three rows and columns avoid
            # passing a large drape based on a single incidental contact.
            enough_support = bool(gaps)
            if draped:
                enough_support = (len(samples) >= 9 and len({round(s["xy"][0], 6) for s in samples}) >= 3
                                  and len({round(s["xy"][1], 6) for s in samples}) >= 3)
            checks.append({"name": source.name, "support_parts": [part.name for part in supports],
                           "sample_count": len(gaps), "median_gap_m": median,
                           "min_gap_m": min(gaps) if gaps else None,
                           "max_gap_m": max(gaps) if gaps else None,
                           "maximum_median_gap_m": maximum_gap,
                           "maximum_penetration_m": maximum_penetration,
                           "samples": samples,
                           "sampling": "13x13 central grid on anatomical footprints; off-body spans reported separately" if draped else "3x3 central support grid",
                           "off_body_span_samples": bridges,
                           "passed": enough_support and median <= maximum_gap
                           and min(gaps) >= -maximum_penetration})
    return checks


def audit_parts(parts, tolerance=.0015):
    """Find actual connected paths to floor; never compare authored coordinates."""
    if not 0 < tolerance <= .01:
        raise ValueError("Contact tolerance must be between zero and 10 mm")
    issues, assemblies = [], {}
    exact = bool(parts) and all(part.bvh is not None for part in parts)
    floor = next((part for part in parts if part.name == "Floor slab"), None)
    if floor is None:
        raise ValueError("Pre-merge Floor slab is missing; merged material meshes are not auditable")
    grouped = defaultdict(list)
    for part in parts:
        if (len(part.low) != 3 or len(part.high) != 3
                or not all(math.isfinite(value) for value in part.low + part.high)
                or any(a >= b for a, b in zip(part.low, part.high))):
            issues.append({"kind": "invalid_bounds", "name": part.name})
        if part.assembly in ASSEMBLIES:
            grouped[part.assembly].append(part)
    for missing in sorted(ASSEMBLIES - set(grouped)):
        issues.append({"kind": "missing_assembly", "assembly": missing})
    for assembly, members in sorted(grouped.items()):
        counts = defaultdict(int)
        for part in members:
            counts[semantic_name(part.name)] += 1
        for required, minimum in REQUIRED_PARTS[assembly].items():
            if counts[required] < minimum:
                issues.append({"kind": "missing_required_part", "assembly": assembly, "name": required,
                               "expected_minimum": minimum, "actual_count": counts[required]})
        for fixture, mount, ratio in (("Brushed handle", "Wardrobe handle mounting post", 2),
                                      ("Drawer pull", "Drawer pull mounting post", 2)):
            if counts[fixture] and counts[mount] < ratio * counts[fixture]:
                issues.append({"kind": "missing_fixture_mounts", "assembly": assembly, "name": mount,
                               "expected_minimum": ratio * counts[fixture], "actual_count": counts[mount]})
        if assembly == "hospital_bed" and not (counts["Sage patient blanket"] or counts["patient_contoured_blanket"]):
            issues.append({"kind": "missing_required_part", "assembly": assembly, "name": "bed blanket"})
        nodes = [floor, *members]
        graph = {index: set() for index in range(len(nodes))}
        edges = []
        cache = {}

        def gap(i, j):
            key = tuple(sorted((i, j)))
            if key not in cache:
                cache[key] = surface_gap(nodes[i], nodes[j])
            return cache[key]

        for i, part in enumerate(nodes):
            if i and part.low[2] < floor.high[2] - .005:
                issues.append({"kind": "floor_penetration", "assembly": assembly, "name": part.name,
                               "penetration_m": floor.high[2] - part.low[2]})
            for j in range(i):
                # Millimetre cloth-shell offsets prevent z-fighting; rigid
                # hardware still uses the tighter contact tolerance.
                pair_tolerance = max(tolerance, .006) if is_soft_layer(part) or is_soft_layer(nodes[j]) else tolerance
                if bounds_gap(part, nodes[j]) <= pair_tolerance and gap(i, j) <= pair_tolerance:
                    graph[i].add(j)
                    graph[j].add(i)
                    edges.append([part.name, nodes[j].name])
        grounded, pending = set(), deque([0])
        while pending:
            index = pending.popleft()
            if index in grounded:
                continue
            grounded.add(index)
            pending.extend(graph[index] - grounded)
        remaining = set(range(1, len(nodes))) - grounded
        components = []
        while remaining:
            component, pending = set(), deque([min(remaining)])
            while pending:
                index = pending.popleft()
                if index in component:
                    continue
                component.add(index)
                pending.extend(graph[index] - component)
            remaining -= component
            components.append(component)
        for component in components:
            candidates = sorted((bounds_gap(nodes[i], nodes[j]), i, j) for i in component for j in range(len(nodes)) if j not in component)
            nearest, pair = math.inf, None
            for lower_bound, i, j in candidates:
                if lower_bound > nearest:
                    break
                distance = gap(i, j)
                if distance < nearest:
                    nearest, pair = distance, (nodes[i].name, nodes[j].name)
            issues.append({"kind": "unsupported_component", "assembly": assembly,
                           "parts": [nodes[index].name for index in sorted(component)],
                           "nearest_pair": list(pair) if pair else None,
                           "nearest_gap_m": nearest if math.isfinite(nearest) else None})
        assemblies[assembly] = {"part_count": len(members), "grounded_parts": len(grounded) - 1,
                                "floor_contacts": [nodes[index].name for index in sorted(graph[0])],
                                "connection_edges": edges, "unsupported_components": len(components)}
    bedding = _bedding_checks(grouped["hospital_bed"]) if exact else []
    for check in bedding:
        if not check["passed"]:
            issues.append({"kind": "bedding_support_gap", **check})
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "passed": not issues,
            "method": "evaluated_mesh_bvh" if exact else "bounds_only",
            "surface_contacts_verified": exact, "tolerance_m": tolerance,
            "soft_layer_contact_tolerance_m": max(tolerance, .006),
            "part_count": len(parts) - 1, "assemblies": assemblies, "bedding": bedding, "issues": issues,
            "limitations": ["Connectivity does not prove load capacity or furniture safety",
                            "Bounds overlap alone cannot prove actual surface contact" if not exact else
                            "BVH intersections and sampled nearest surfaces establish visual contact, not engineering joints",
                            "Walls, external plants and decorative foliage are outside this furniture audit"]}


def audit_scene(objects=None, output=None, tolerance=.0015):
    report = audit_parts(collect_scene(objects), tolerance)
    if output:
        write_report(report, output)
    return report


def write_report(report, output):
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")


def _build_room_only(path):
    """Execute this trusted repository builder only up to its first room() call."""
    path = Path(path).resolve()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    cutoff = next((i for i, statement in enumerate(tree.body)
                   if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
                   and isinstance(statement.value.func, ast.Name) and statement.value.func.id == "room"), None)
    if cutoff is None:
        raise ValueError("Builder has no top-level room() boundary; refusing to run exports")
    namespace = {"__file__": str(path), "__name__": "room_visual_audit_builder"}
    exec(compile(ast.Module(body=tree.body[:cutoff], type_ignores=[]), str(path), "exec"), namespace)
    namespace["room"]()
    return namespace["room_objects"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--manifest")
    inputs.add_argument("--scene", action="store_true")
    inputs.add_argument("--builder")
    parser.add_argument("--output", default="artifacts/room-visual-audit.json")
    parser.add_argument("--tolerance", type=float, default=.0015)
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(arguments)
    if args.manifest:
        report = audit_parts(collect_manifest(args.manifest), args.tolerance)
        report["source"] = args.manifest
    else:
        report = audit_scene(_build_room_only(args.builder) if args.builder else None, tolerance=args.tolerance)
        report["source"] = args.builder or "current Blender pre-merge scene"
        if args.builder:
            report["builder_sha256"] = hashlib.sha256(Path(args.builder).read_bytes()).hexdigest()
    write_report(report, args.output)
    print(json.dumps({"passed": report["passed"], "method": report["method"], "part_count": report["part_count"], "issues": report["issues"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
