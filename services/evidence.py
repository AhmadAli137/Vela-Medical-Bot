"""Provenance-aware research data; scores are product hypotheses, never survey estimates."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SIGNALS = ("frequency_signal", "severity_signal", "frustration_signal", "staff_time_signal",
           "workflow_disruption_signal", "embodiment_value", "robot_solvability",
           "crowded_market_penalty", "regulatory_complexity", "patient_autonomy_gain", "clinical_risk")
APPROVED_RIGHTS = {"open_license_verified", "permission_verified"}


def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_painpoint(point: dict) -> dict:
    for name in ("id", "stakeholder", "source", "normalized_summary", "theme", "source_citations", "score_basis"):
        if not point.get(name):
            raise ValueError(f"Missing {name}")
    if point["stakeholder"] not in {"patient", "nurse", "staff", "physician", "mixed"}:
        raise ValueError("Unknown stakeholder")
    for name in SIGNALS:
        value = point.get(name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or not 0 <= value <= 5):
            raise ValueError(f"{name} must be null or a finite 0–5 hypothesis score")
    if point["score_basis"] != "product_hypothesis_not_survey_measurement":
        raise ValueError("Scoring needs explicit hypothesis attribution")
    minutes = point.get("estimated_staff_minutes_saved")
    if minutes is not None and (isinstance(minutes, bool) or not isinstance(minutes, (int, float))
                                or not math.isfinite(minutes) or minutes < 0):
        raise ValueError("Time savings must be null or a finite nonnegative measurement")
    if minutes is not None and not point.get("time_savings_measurement_source"):
        raise ValueError("Time savings require a measurement source; use null until measured")
    return point


def rank_opportunities(points: list[dict]) -> list[dict]:
    """Penalize risk/crowding and multiply by embodiment; zero embodiment scores zero."""
    ranked = []
    for original in points:
        point = validate_painpoint(dict(original))
        val = lambda name: float(point.get(name) or 0)
        benefit = (1.5 * val("patient_autonomy_gain") + val("staff_time_signal")
                   + val("workflow_disruption_signal") + val("robot_solvability"))
        penalty = (2 * val("clinical_risk") + val("regulatory_complexity")
                   + val("crowded_market_penalty"))
        point["opportunity_score"] = round(max(0, benefit - penalty) * val("embodiment_value") / 5, 2)
        point["ranking_version"] = "hypothesis-v1"
        ranked.append(point)
    return sorted(ranked, key=lambda item: (-item["opportunity_score"], item["id"]))


def import_feedback(csv_path: Path, source: dict, *, privacy_attestation: str,
                    intended_use: str = "research") -> list[dict]:
    """Local, explicitly authorized import. No downloaded patient comments or model calls."""
    if source.get("rights_status") not in APPROVED_RIGHTS or not source.get("rights_evidence"):
        raise ValueError("Verified reuse rights and documentary evidence are required")
    if not isinstance(source.get("id"), str) or not source["id"].strip() or not isinstance(source.get("url"), str) or not source["url"].startswith("https://"):
        raise ValueError("Source ID and HTTPS provenance URL are required")
    if intended_use not in {"research", "commercial"}:
        raise ValueError("Unknown intended use")
    if intended_use == "commercial" and source.get("commercial_reuse_allowed") is not True:
        raise ValueError("Commercial reuse is not authorized")
    if privacy_attestation != "human_reviewed_deidentified":
        raise ValueError("Human de-identification review is required before import")
    results = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            original = (row.get("original_text_if_licensed") or "").strip()
            summary = (row.get("normalized_summary") or "").strip()
            if original and source.get("raw_comments_reuse_allowed") is not True:
                raise ValueError(f"Row {row_number}: verbatim comments are not authorized")
            if not summary or len(summary) > 4000 or len(original) > 10000:
                raise ValueError(f"Row {row_number}: missing or overlong summary/text")
            if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b(?:MRN|health card|patient id)\s*[:#]?\s*\w+|\b\d{3}[- .]\d{3}[- .]\d{4}\b", summary + " " + original, re.I):
                raise ValueError(f"Row {row_number}: possible identifiers require further review")
            point = {"id": hashlib.sha256((source["id"] + summary).encode()).hexdigest()[:16],
                     "stakeholder": row.get("stakeholder", "patient"), "source": source["id"],
                     "original_text_if_licensed": original or None, "normalized_summary": summary,
                     "theme": row.get("theme") or "uncategorized", "subtheme": row.get("subtheme") or "review_needed",
                     "source_citations": [source["url"]], "score_basis": "product_hypothesis_not_survey_measurement",
                     "estimated_staff_minutes_saved": None, "evidence_quality": "authorized_import_not_validated",
                     "privacy_status": privacy_attestation, "proposed_robot_intervention": None,
                     "ingested_at": datetime.now(timezone.utc).isoformat()}
            point.update({name: None for name in SIGNALS})
            for name in ("physical_action_required", "navigation_required", "manipulation_required",
                         "conversation_required", "information_access_required"):
                point[name] = None
            results.append(validate_painpoint(point))
    return results


def promotion_errors(record: dict, *, training: bool = False) -> list[str]:
    errors = []
    if record.get("rights_status") not in APPROVED_RIGHTS or not record.get("rights_evidence"):
        errors.append("reuse_rights_unverified")
    if record.get("privacy_status") != "human_reviewed_clear":
        errors.append("privacy_review_required")
    if not record.get("human_reviewer") or not record.get("reviewed_at"):
        errors.append("human_review_required")
    for detector in ("people_detection", "text_detection"):
        if record.get("annotations", {}).get(detector, {}).get("status") != "clear":
            errors.append(f"{detector}_not_clear")
    if not record.get("hash") or not record.get("local_path"):
        errors.append("verified_content_required")
    if record.get("room_type") not in {"single_patient_room", "shared_patient_room", "mock_room", "ward", "interior"}:
        errors.append("room_classification_required")
    if record.get("quality") != "accepted":
        errors.append("quality_review_required")
    if training and record.get("training_permission") is not True:
        errors.append("training_permission_required")
    if training and record.get("commercial_reuse_allowed") is not True:
        errors.append("commercial_training_reuse_not_authorized")
    return errors


def get_research(data_dir: Path | None = None) -> dict:
    directory = data_dir or DATA
    sources = read_json(directory / "source-registry" / "sources.json", [])
    points = read_json(directory / "patient-feedback" / "painpoints.json", [])
    images = read_json(directory / "hospital-images" / "records.json", [])
    seeds = read_json(directory / "hospital-images" / "hospitals.json", [])
    return {"opportunities": rank_opportunities(points), "sources": sources, "images": images,
            "dataset_summary": {"target_hospitals": 50, "target_candidates": 1000,
                "seed_hospitals": len({s["hospital"] for s in seeds}),
                "candidate_records": len(images),
                "candidate_hospitals": len({r["hospital"] for r in images}),
                "downloaded_unique_images": len({r["hash"] for r in images if r.get("hash")}),
                "analysis_approved": sum(r.get("usable_for_analysis") is True and not promotion_errors(r) for r in images),
                "training_approved": sum(r.get("usable_for_training") is True and not promotion_errors(r, training=True) for r in images),
                "quarantined": sum(not r.get("usable_for_analysis") for r in images),
                "coverage_verified": False, "raw_patient_comments": sum(bool(p.get("original_text_if_licensed")) for p in points),
                "score_notice": "Product hypotheses; no measured staff time savings or clinical efficacy."}}
