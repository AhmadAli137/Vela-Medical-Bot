import csv
import io
from copy import deepcopy

import pytest
from PIL import Image

from services.evidence import (DATA, get_research, import_feedback, promotion_errors,
                               rank_opportunities, read_json, validate_painpoint)
from scripts.acquire_images import (PageImages, RestrictedFetcher, allowed_url, candidate,
                                    download)


def point():
    return deepcopy(get_research()["opportunities"][0])


def csv_file(tmp_path, *, summary="Personal item out of reach", original=""):
    path = tmp_path / "feedback.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["normalized_summary", "original_text_if_licensed", "stakeholder"])
        writer.writeheader()
        writer.writerow({"normalized_summary": summary, "original_text_if_licensed": original, "stakeholder": "patient"})
    return path


def permitted_source():
    return {"id": "local_test", "url": "https://example.org/authorized", "rights_status": "permission_verified",
            "rights_evidence": "test permission fixture", "commercial_reuse_allowed": False,
            "raw_comments_reuse_allowed": False}


def test_seed_hospitals_are_distinct_and_target_not_acquired_count():
    research = get_research()
    seeds = read_json(DATA / "hospital-images" / "hospitals.json")
    assert len({h["hospital"] for h in seeds}) == 50
    assert sum(h["target_candidates"] for h in seeds) == 1000
    assert research["dataset_summary"]["candidate_records"] == len(research["images"])
    assert research["dataset_summary"]["raw_patient_comments"] == 0


def test_low_embodiment_problem_is_scored_down():
    high = point()
    low = {**high, "id": "low", "embodiment_value": 0}
    high["embodiment_value"] = 5
    ranking = rank_opportunities([low, high])
    assert ranking[-1]["id"] == "low"
    assert ranking[-1]["opportunity_score"] == 0
    risky = {**high, "clinical_risk": 5}
    assert rank_opportunities([risky])[0]["opportunity_score"] < ranking[0]["opportunity_score"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 6, True, "high"])
def test_invalid_score_rejected(value):
    with pytest.raises(ValueError):
        validate_painpoint({**point(), "embodiment_value": value})


def test_no_invented_time_savings():
    with pytest.raises(ValueError, match="measurement source"):
        validate_painpoint({**point(), "estimated_staff_minutes_saved": 12})


def test_feedback_requires_rights_and_review(tmp_path):
    source = permitted_source()
    path = csv_file(tmp_path)
    with pytest.raises(ValueError, match="Verified reuse"):
        import_feedback(path, {**source, "rights_status": "unknown"}, privacy_attestation="human_reviewed_deidentified")
    with pytest.raises(ValueError, match="Commercial reuse"):
        import_feedback(path, source, privacy_attestation="human_reviewed_deidentified", intended_use="commercial")
    with pytest.raises(ValueError, match="Human de-identification"):
        import_feedback(path, source, privacy_attestation="automatic_redaction")
    output = import_feedback(path, source, privacy_attestation="human_reviewed_deidentified")
    assert len(output) == 1
    assert output[0]["frequency_signal"] is None
    assert output[0]["estimated_staff_minutes_saved"] is None


def test_verbatim_requires_explicit_permission(tmp_path):
    with pytest.raises(ValueError, match="verbatim"):
        import_feedback(csv_file(tmp_path, original="An authorized test comment"), permitted_source(),
                        privacy_attestation="human_reviewed_deidentified")


@pytest.mark.parametrize("summary", ["Contact me at somebody@example.org", "Patient id: 1234", "Call 416-555-0100"])
def test_identifiers_quarantined_even_after_attestation(tmp_path, summary):
    with pytest.raises(ValueError, match="identifiers"):
        import_feedback(csv_file(tmp_path, summary=summary), permitted_source(),
                        privacy_attestation="human_reviewed_deidentified")


@pytest.mark.parametrize("url", ["http://hospital.example/room", "https://hospital.example.evil/room",
                                 "https://user:pass@hospital.example/room", "https://hospital.example:444/room",
                                 "https://127.0.0.1/room", "file:///room"])
def test_crawler_domain_and_scheme_boundary(url):
    assert not allowed_url(url, ["hospital.example"])


def test_robots_unavailable_and_denied_fail_closed(monkeypatch):
    fetcher = RestrictedFetcher(["hospital.example"])
    monkeypatch.setattr(fetcher, "_fetch", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")))
    assert not fetcher.can_fetch("https://hospital.example/room")
    with pytest.raises(ValueError, match="offline"):
        fetcher.fetch("https://hospital.example/room")
    fetcher = RestrictedFetcher(["hospital.example"])
    monkeypatch.setattr(fetcher, "_fetch", lambda *args, **kwargs: (b"User-agent: *\nDisallow: /private\n", "text/plain", args[0]))
    assert not fetcher.can_fetch("https://hospital.example/private/room")
    assert fetcher.can_fetch("https://hospital.example/room")


def test_missing_directives_do_not_allow_crawling(monkeypatch):
    fetcher = RestrictedFetcher(["hospital.example"])
    monkeypatch.setattr(fetcher, "_fetch", lambda *args, **kwargs: (b"Not found", "text/plain", args[0]))
    assert not fetcher.can_fetch("https://hospital.example/room")


def test_parser_metadata_is_not_treated_as_reviewed_content():
    parser = PageImages()
    parser.feed('<img data-src="/room.jpg" alt="Patient room"><source srcset="/small.jpg 100w, /large.jpg 800w">')
    assert ("/room.jpg", "Patient room") in parser.images
    assert ("/large.jpg", "") in parser.images
    record = candidate({"hospital": "Test hospital"}, "https://hospital.example/room", "https://hospital.example/room.jpg", "Patient room")
    errors = promotion_errors(record)
    assert "people_detection_not_clear" in errors
    assert "text_detection_not_clear" in errors
    assert "reuse_rights_unverified" in errors
    assert record["usable_for_training"] is False


def test_download_needs_exact_image_permission_and_hash_deduplicates(tmp_path, monkeypatch):
    url = "https://hospital.example/room.png"
    record = candidate({"hospital": "Test"}, "https://hospital.example/room", url, "Test mock room")
    stream = io.BytesIO()
    Image.new("RGB", (300, 300), "white").save(stream, format="PNG")
    class Fetch:
        def fetch(self, url):
            return stream.getvalue(), "image/png", url
    with pytest.raises(ValueError, match="licence"):
        download(record, Fetch(), tmp_path, {})
    permission = {"image_url": url, "rights_status": "permission_verified", "rights_evidence": "Synthetic test fixture created in test"}
    monkeypatch.setattr("scripts.acquire_images.detect_privacy", lambda path: {"people_detection": {"status": "unknown"}, "text_detection": {"status": "unknown"}})
    download(record, Fetch(), tmp_path, permission)
    other = deepcopy(record)
    download(other, Fetch(), tmp_path, permission)
    assert record["hash"] == other["hash"]
    assert len(list((tmp_path / "quarantine").iterdir())) == 1
    assert record["usable_for_analysis"] is False
    assert "people_detection_not_clear" in promotion_errors(record)
    with pytest.raises(ValueError, match="exact image"):
        download(record, Fetch(), tmp_path, {**permission, "image_url": url + "?other"})


def test_training_has_separate_permission_gate():
    record = {"rights_status": "permission_verified", "rights_evidence": "test fixture", "privacy_status": "human_reviewed_clear",
              "human_reviewer": "test-reviewer", "reviewed_at": "2026-09-12", "hash": "test-hash", "local_path": "test.png",
              "room_type": "mock_room", "quality": "accepted", "annotations": {"people_detection": {"status": "clear"}, "text_detection": {"status": "clear"}}}
    assert promotion_errors(record) == []
    assert "training_permission_required" in promotion_errors(record, training=True)
    assert "commercial_training_reuse_not_authorized" in promotion_errors(record, training=True)
