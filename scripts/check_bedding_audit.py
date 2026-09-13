"""Blender regression fixtures for draped-cloth support classification.

blender --background --factory-startup --python scripts/check_bedding_audit.py
No source scene, exports or rendering are needed.
"""
import json
from pathlib import Path
import sys

from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_room_visuals import Part, _bedding_checks


def compound(name, boxes):
    vertices, polygons = [], []
    faces = ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
    for low, high in boxes:
        x, y, z = low
        a, b, c = high
        start = len(vertices)
        vertices.extend(Vector(v) for v in ((x, y, z), (a, y, z), (a, b, z), (x, b, z),
                                            (x, y, c), (a, y, c), (a, b, c), (x, b, c)))
        polygons.extend(tuple(start + index for index in face) for face in faces)
    low = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
    high = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
    return Part(name, "hospital_bed", low, high, vertex_count=len(vertices), polygon_count=len(polygons),
                vertices=vertices, bvh=BVHTree.FromPolygons(vertices, polygons, all_triangles=False))


legs = [((1.195, .70, .89), (1.345, 1.40, 1.005)),
        ((1.455, .70, .89), (1.605, 1.40, 1.005))]
sheet = compound("Fitted cotton sheet", [((1., .60, .88), (1.8, 1.50, .888))])


def check(label, underside, body_boxes, expected):
    blanket = compound("patient_contoured_blanket", [((1.05, .65, underside), (1.75, 1.45, underside + .003))])
    parts = [sheet, blanket]
    if body_boxes:
        parts.append(compound("patient_anatomical_skin", body_boxes))
    report = _bedding_checks(parts)[0]
    assert report["passed"] is expected, (label, report)
    return {"case": label, "expected_pass": expected, "actual_pass": report["passed"],
            "anatomical_samples": report["sample_count"],
            "off_body_span_samples": len(report["off_body_span_samples"]),
            "median_gap_m": report["median_gap_m"], "min_gap_m": report["min_gap_m"]}


results = [check("supported blanket bridges separate legs", 1.009, legs, True),
           check("blanket lifted 25 mm from its supporting legs", 1.034, legs, False),
           check("blanket penetrates supporting legs", .975, legs, False),
           check("hand above blanket is not its supporting surface", 1.009,
                 legs + [((1.18, .90, 1.030), (1.36, 1.17, 1.08))], True),
           check("no anatomical support cannot pass", 1.009, [], False)]
output = ROOT / "artifacts" / "bedding-audit-regressions.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"passed": True, "fixture_geometry": "synthetic closed meshes in metres",
                              "cases": results}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"passed": True, "cases": len(results), "report": str(output)}))
