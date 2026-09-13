"""Furniture-audit regressions; bounds fixtures do not claim mesh contact."""
import json

from scripts.audit_room_visuals import Part, _build_room_only, audit_parts


def part(name, center, dimensions, assembly="patient_tray"):
    return Part(name,assembly,[c-d/2 for c,d in zip(center,dimensions)],
                [c+d/2 for c,d in zip(center,dimensions)])


def tray_fixture(tire_height=.045):
    parts=[part("Floor slab",(0,0,-.05),(7,6,.10),"room_architecture"),
           part("Patient tray tabletop",(.85,1.4,.99),(.60,.64,.045)),
           part("Patient tray underside frame",(.85,1.4,.952),(.56,.60,.04)),
           part("Tray support outer column",(.61,1.4,.45),(.065,.075,.75)),
           part("Tray telescoping support",(.61,1.4,.865),(.043,.052,.21)),
           part("Tray adjustment latch",(.563,1.4,.79),(.045,.075,.025)),
           part("Tray floor spine",(.61,1.4,.10),(.07,.53,.055))]
    for side,y in enumerate((1.15,1.65)):
        parts.append(part(f"Tray floor outrigger.{side:03}",(.85,y,.10),(.54,.065,.055)))
        for corner,x in enumerate((.61,1.09)):
            suffix=side*2+corner
            parts.append(part(f"Tray caster tire.{suffix:03}",(x,y,tire_height),(.09,.038,.09)))
            parts.append(part(f"Tray caster stem.{suffix:03}",(x,y,.085),(.024,.024,.05)))
    for index,y in enumerate((1.22,1.48)):
        parts.append(part(f"Tray object landing pad.{index:03}",(.85,y,1.03),(.05,.12,.035)))
    return parts


def test_tray_complete_graph_connects_all_parts_and_detects_floating_wheels():
    grounded=audit_parts(tray_fixture())
    tray=grounded["assemblies"]["patient_tray"]
    assert tray["part_count"]==18
    assert tray["grounded_parts"]==18
    assert len(tray["floor_contacts"])==4
    assert not any(issue.get("assembly")=="patient_tray" for issue in grounded["issues"])
    floating=audit_parts(tray_fixture(tire_height=.055))
    unsupported=[issue for issue in floating["issues"] if issue.get("assembly")=="patient_tray" and issue["kind"]=="unsupported_component"]
    assert unsupported
    assert abs(unsupported[0]["nearest_gap_m"]-.01)<1e-9
    assert not floating["surface_contacts_verified"]


def test_tray_missing_stem_is_reported_but_legacy_rooms_do_not_require_tray():
    incomplete=[item for item in tray_fixture() if item.name!="Tray caster stem.003"]
    report=audit_parts(incomplete)
    missing=[issue for issue in report["issues"] if issue.get("name")=="Tray caster stem"]
    assert len(missing)==1 and missing[0]["actual_count"]==3
    legacy=audit_parts(tray_fixture()[:1])
    assert "patient_tray" not in legacy["assemblies"]
    assert not any(issue.get("assembly")=="patient_tray" for issue in legacy["issues"])


def test_room_only_builder_calls_optional_furniture_but_never_export_suffix(tmp_path):
    builder=tmp_path/"fixture.py"
    builder.write_text("from pathlib import Path\nROOT=Path(__file__).parent\nroom_objects=[]\n"
                       "def room(): room_objects.append('room')\n"
                       "def assistance_room(descriptors): room_objects.append('tray')\n"
                       "room()\nraise RuntimeError('export suffix must not execute')\n",encoding="utf-8")
    directory=tmp_path/"sim"
    directory.mkdir()
    descriptors=directory/"reference_body_descriptors.json"
    descriptors.write_text(json.dumps({"body_specs":[{"name":"meal_box"}]}),encoding="utf-8")
    assert _build_room_only(builder)==["room","tray"]
    descriptors.write_text(json.dumps({"body_specs":[{"name":"phone"}]}),encoding="utf-8")
    assert _build_room_only(builder)==["room"]
    builder.write_text("room_objects=[]\ndef room(): room_objects.append('legacy')\nroom()\n"
                       "raise RuntimeError('export suffix must not execute')\n",encoding="utf-8")
    assert _build_room_only(builder)==["legacy"]
