"""Recreate curated source and hypothesis records (does not acquire datasets)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.evidence import DATA, SIGNALS, write_json


def main():
    source_rows = [
        ("nhs_inpatient", "CQC Adult Inpatient Survey 2025", "https://www.cqc.org.uk/publications/surveys/adult-inpatient-survey", 2025, "England", "patient", ["communication", "discharge", "environment", "responsiveness"], "Published survey aggregates; qualitative material availability varies by release."),
        ("hcahps", "CMS HCAHPS", "https://www.cms.gov/medicare/quality/initiatives/hospital-quality-initiative/hcahps-patients-perspectives-care-survey", None, "United States", "patient", ["staff responsiveness", "care coordination", "communication", "environment", "discharge information"], "Public hospital aggregates; individual patient comments are not included in this corpus."),
        ("cpes_ic", "CIHI Canadian Patient Experiences Survey — Inpatient Care", "https://www.cihi.ca/en/patient-experience", None, "Canada", "patient", ["inpatient experience", "patient-centred care"], "Instrument/resource toolkit. Historical respondent data require CIHI data request; none obtained."),
        ("care_opinion", "Care Opinion data access", "https://www.careopinion.org.uk/info/api", None, "United Kingdom", "patient", ["narrative feedback"], "Licence/API terms require verification before any import; no stories copied or acquired."),
        ("patient_ombudsman", "Ontario Patient Ombudsman 2024/25 annual report", "https://patientombudsman.ca/Publications/Annual-Highlights/2024-25", 2025, "Ontario, Canada", "patient", ["complaints", "health-care experience"], "Complaint themes are not representative population prevalence; published summaries only."),
        ("nhs_staff", "NHS Staff Survey 2025 national results", "https://www.nhsstaffsurveys.com/results/national-results/", 2025, "England", "staff", ["staff experience", "workload", "wellbeing"], "Published national and organizational aggregates. Raw staff comments not obtained."),
        ("sops", "AHRQ SOPS Hospital Database", "https://www.ahrq.gov/sops/databases/hospital/index.html", 2024, "United States", "staff", ["staffing and work pace", "teamwork", "handoffs", "safety culture"], "Public aggregate reports; respondent-level research data require separate application."),
        ("cfnu", "CFNU 2026 Member Survey Summary Report", "https://nursesunions.ca/research/2026-cfnu-member-survey-summary-report/", 2026, "Canada", "nurse", ["nursing work life", "workload"], "Member survey, not all nurses; no raw responses acquired."),
        ("cma", "CMA National Physician Health Survey reports", "https://www.cma.ca/physician-wellness-hub/resources/national-physician-health-survey-reports", 2025, "Canada", "physician", ["administrative burden", "physician wellness"], "Administrative burden is largely a software/workflow issue; not evidence of robot time savings."),
        ("hopkins_room", "Johns Hopkins Medicine: Your Hospital Room", "https://www.hopkinsmedicine.org/patient-care/patients-visitors/admission-discharge/hospital-room", None, "United States", "patient", ["room configuration", "room cleaning", "medical alarms"], "Institutional room guidance supports object/workflow context; not a pain-point prevalence study."),
    ]
    sources = []
    for sid, title, url, year, geography, stakeholder, measures, note in source_rows:
        sources.append({"id": sid, "title": title, "url": url, "provenance": "official_publisher_public_page",
            "source_tier": 2, "accessed_at": "2026-09-12", "year": year, "geography": geography,
            "stakeholder": stakeholder, "sample_size": None,
            "sample_size_note": "Not transcribed; consult exact release/methodology before numerical analysis.",
            "structured_measures": measures, "raw_comments_exist": "not_verified" if sid == "care_opinion" else "not_acquired",
            "licence": "not_verified_for_dataset_reuse", "rights_status": "summary_only",
            "rights_evidence": None, "commercial_reuse_allowed": False, "raw_comments_reuse_allowed": False,
            "commercial_reuse_constraints": "No grant inferred from public access; source-specific permission/licence review required.",
            "privacy_considerations": "Do not ingest person-identifiable narratives, staff details or patient records; no PHI sent to model APIs.",
            "content_acquired": "citation_and_brief_paraphrase_only", "notes": note})
    by_id = {s["id"]: s for s in sources}
    by_id["care_opinion"].update({"licence": "CC BY-NC-SA 4.0 for published feedback; commercial licence required",
        "rights_evidence": "https://www.careopinion.org.uk/info/api", "raw_comments_exist": True,
        "commercial_reuse_constraints": "Official terms updated 2026-08-24 specify non-commercial reuse; request a commercial licence before use in this product.",
        "notes": "Licence verified from official public terms; no stories acquired. Summary-only project record does not authorize raw import."})
    by_id["nhs_staff"]["sample_size_note"] = "Publisher says over 760,000 respondents in autumn 2025; exact denominator not transcribed."
    by_id["cfnu"]["sample_size_note"] = "Publisher says nearly 5,000 nurses; exact denominator not transcribed."
    by_id["nhs_inpatient"]["verification_note"] = "Current official 2025 report discovered through indexed official source; direct open returned 403, so no source scraping or raw acquisition attempted."
    rows = [
        ("personal_item_reach", "Personal items within reach", "patient", ["hcahps", "hopkins_room"], "patient_autonomy", "personal items", "Staff responsiveness is a measured experience domain. The specific value of retrieving phones or glasses is a product hypothesis requiring direct observation.", "Retrieve an explicitly permitted personal item to a reachable surface in a mock room.", 5, 3, 3, 4, 1, 1, 2, 5, True, True, True, True, False, "phone retrieval / accessible placement"),
        ("room_readiness", "Verify room readiness", "staff", ["sops", "hopkins_room"], "room_operations", "readiness", "Work pace and handoffs are measured staff concerns. Room-state verification is an inferred intervention; published surveys do not establish its time savings.", "Compare observed clear zones and approved objects with a staff-defined room template; report exceptions.", 5, 4, 4, 4, 1, 1, 2, 3, True, True, False, False, False, "scan / semantic state diff"),
        ("equipment_search", "Locate permitted equipment", "nurse", ["nhs_staff", "sops", "cfnu"], "workload", "search", "Staff surveys provide workload context but do not isolate equipment-search minutes in this seed corpus.", "Locate permitted assets with RTLS plus visual context; let staff decide retrieval.", 4, 4, 4, 3, 1, 3, 2, 2, True, True, False, True, True, "asset location / RTLS mock"),
        ("what_next", "Explain what happens next", "patient", ["nhs_inpatient", "hcahps", "cpes_ic"], "communication", "status uncertainty", "Patient-experience instruments include communication and discharge information. Verified operational status may reduce uncertainty; a mobile manipulator is usually unnecessary.", "Show authenticated hospital status with source and freshness; route unanswered questions to staff.", 0, 3, 3, 5, 1, 4, 3, 3, False, False, False, True, True, "authoritative information adapter"),
        ("environment_controls", "Accessible room controls", "patient", ["hcahps", "hopkins_room"], "environment", "control access", "Hospital environment is an experience domain. Difficulty reaching non-clinical room controls is an intervention hypothesis, not a quantified finding here.", "Prefer supported digital controls for lighting/blinds; use physical manipulation only on validated fixtures.", 2, 2, 2, 4, 1, 4, 2, 4, True, False, True, True, True, "mock non-clinical fixture"),
        ("discharge_logistics", "Coordinate discharge belongings", "patient", ["nhs_inpatient", "patient_ombudsman", "hcahps"], "discharge", "logistics", "Discharge is covered in patient-experience reporting. Belongings checks and equipment location are non-clinical hypotheses, separate from clinical discharge decisions.", "Check a consented belongings zone and locate transport equipment; show status from the hospital system.", 3, 3, 3, 3, 2, 3, 3, 3, True, True, False, True, True, "discharge-ready semantic template"),
        ("room_reset", "Restore approved room objects", "staff", ["sops", "hopkins_room"], "room_operations", "object configuration", "Room cleaning and furniture context are documented institutionally. Automated room reset has no efficacy evidence in this corpus.", "Reposition only allowlisted mock props toward a desired semantic state; verify each change.", 5, 4, 4, 2, 2, 2, 3, 3, True, True, True, False, False, "room reset / policy abstention"),
        ("physician_admin", "Reduce physician paperwork", "physician", ["cma"], "administration", "burden", "CMA physician reporting addresses administrative burden. Its direct embodiment value is low and this platform should not treat paperwork as a manipulation problem.", "Integrate verified operational events into existing systems if useful; prioritize workflow/software alternatives.", 0, 4, 4, 3, 1, 5, 4, 1, False, False, False, True, True, "digital workflow alternative"),
        ("nonclinical_requests", "Route service requests", "patient", ["hcahps", "nhs_inpatient"], "responsiveness", "service routing", "Responsiveness and communication are measured domains. Automated routing must be tested for extra staff burden and false escalation.", "Route food, linen and cleaning requests into a configured staff workflow; preserve clinical escalation.", 1, 3, 3, 4, 1, 4, 2, 3, False, False, False, True, True, "deterministic request router"),
        ("clutter_verification", "Notice blocked clear zones", "mixed", ["hopkins_room", "sops"], "room_operations", "clutter", "Room features and safety culture justify studying clear-zone observation. These sources do not show that robot monitoring prevents falls.", "Observe geometric obstruction hypotheses and ask staff to confirm; never move patients or attached equipment.", 4, 3, 4, 4, 2, 2, 2, 3, True, True, False, False, False, "clearance observation / blocked path benchmark"),
    ]
    points = []
    for row in rows:
        sid, title, stakeholder, refs, theme, subtheme, summary, intervention, embodiment, staff, disruption, solvability, risk, market, regulatory, autonomy, physical, nav, manip, convo, info, scenario = row
        point = {"id": sid, "title": title, "stakeholder": stakeholder, "source": refs[0],
            "original_text_if_licensed": None, "normalized_summary": summary, "theme": theme, "subtheme": subtheme,
            "frequency_signal": None, "severity_signal": None, "frustration_signal": None,
            "staff_time_signal": staff, "workflow_disruption_signal": disruption,
            "physical_action_required": physical, "navigation_required": nav, "manipulation_required": manip,
            "conversation_required": convo, "information_access_required": info, "clinical_risk": risk,
            "embodiment_value": embodiment, "robot_solvability": solvability,
            "crowded_market_penalty": market, "regulatory_complexity": regulatory,
            "estimated_staff_minutes_saved": None, "patient_autonomy_gain": autonomy,
            "proposed_robot_intervention": intervention, "evidence_quality": "official_context_indirect_robot_need",
            "source_citations": [by_id[r]["url"] for r in refs],
            "score_basis": "product_hypothesis_not_survey_measurement", "scenario": scenario,
            "validation_required": "Hospital interviews, observation, controlled comparison and safety review before efficacy claims."}
        points.append(point)
    write_json(DATA / "source-registry" / "sources.json", sources)
    write_json(DATA / "patient-feedback" / "painpoints.json", points)
    hospital_rows = [
        ("toronto_general", "Toronto General Hospital", "Canada", "www.uhn.ca"),
        ("toronto_western", "Toronto Western Hospital", "Canada", "www.uhn.ca"),
        ("princess_margaret", "Princess Margaret Cancer Centre", "Canada", "www.uhn.ca"),
        ("sunnybrook", "Sunnybrook Health Sciences Centre", "Canada", "sunnybrook.ca"),
        ("mount_sinai", "Mount Sinai Hospital Toronto", "Canada", "www.sinaihealth.ca"),
        ("st_michaels", "St. Michael's Hospital Toronto", "Canada", "unityhealth.to"),
        ("sickkids", "The Hospital for Sick Children", "Canada", "www.sickkids.ca"),
        ("north_york", "North York General Hospital", "Canada", "www.nygh.on.ca"),
        ("humber_river", "Humber River Health Hospital", "Canada", "www.hrh.ca"),
        ("oakville", "Oakville Trafalgar Memorial Hospital", "Canada", "www.haltonhealthcare.on.ca"),
        ("credit_valley", "Credit Valley Hospital", "Canada", "www.thp.ca"),
        ("mississauga", "Mississauga Hospital", "Canada", "www.thp.ca"),
        ("hamilton_general", "Hamilton General Hospital", "Canada", "www.hamiltonhealthsciences.ca"),
        ("juravinski", "Juravinski Hospital", "Canada", "www.hamiltonhealthsciences.ca"),
        ("mcmaster", "McMaster Children's Hospital", "Canada", "www.hamiltonhealthsciences.ca"),
        ("ottawa_civic", "The Ottawa Hospital Civic Campus", "Canada", "www.ottawahospital.on.ca"),
        ("ottawa_general", "The Ottawa Hospital General Campus", "Canada", "www.ottawahospital.on.ca"),
        ("kingston", "Kingston General Hospital", "Canada", "kingstonhsc.ca"),
        ("london_victoria", "Victoria Hospital London", "Canada", "www.lhsc.on.ca"),
        ("london_university", "University Hospital London", "Canada", "www.lhsc.on.ca"),
        ("vancouver_general", "Vancouver General Hospital", "Canada", "www.vch.ca"),
        ("st_pauls", "St. Paul's Hospital Vancouver", "Canada", "www.providencehealthcare.org"),
        ("bc_children", "BC Children's Hospital", "Canada", "www.bcchildrens.ca"),
        ("royal_columbian", "Royal Columbian Hospital", "Canada", "www.fraserhealth.ca"),
        ("surrey_memorial", "Surrey Memorial Hospital", "Canada", "www.fraserhealth.ca"),
        ("foothills", "Foothills Medical Centre", "Canada", "www.albertahealthservices.ca"),
        ("south_health", "South Health Campus", "Canada", "www.albertahealthservices.ca"),
        ("ualberta", "University of Alberta Hospital", "Canada", "www.albertahealthservices.ca"),
        ("royal_alexandra", "Royal Alexandra Hospital", "Canada", "www.albertahealthservices.ca"),
        ("winnipeg_hsc", "Health Sciences Centre Winnipeg", "Canada", "hsc.mb.ca"),
        ("st_boniface", "St. Boniface Hospital", "Canada", "stbonifacehospital.ca"),
        ("royal_victoria", "Royal Victoria Hospital Montreal", "Canada", "muhc.ca"),
        ("jewish_general", "Jewish General Hospital", "Canada", "www.jgh.ca"),
        ("chum", "Centre hospitalier de l'Universite de Montreal", "Canada", "www.chumontreal.qc.ca"),
        ("qeii", "QEII Health Sciences Centre Halifax Infirmary", "Canada", "www.nshealth.ca"),
        ("iwk", "IWK Health Centre", "Canada", "iwkhealth.ca"),
        ("stanford", "Stanford Hospital", "United States", "stanfordhealthcare.org"),
        ("hopkins", "The Johns Hopkins Hospital", "United States", "www.hopkinsmedicine.org"),
        ("mayo_st_marys", "Mayo Clinic Hospital Saint Marys Campus", "United States", "www.mayoclinic.org"),
        ("cleveland", "Cleveland Clinic Main Campus Hospital", "United States", "my.clevelandclinic.org"),
        ("mass_general", "Massachusetts General Hospital", "United States", "www.massgeneral.org"),
        ("brigham", "Brigham and Women's Hospital", "United States", "www.brighamandwomens.org"),
        ("ucla", "Ronald Reagan UCLA Medical Center", "United States", "www.uclahealth.org"),
        ("ucsf", "UCSF Medical Center at Mission Bay", "United States", "www.ucsfhealth.org"),
        ("penn", "Hospital of the University of Pennsylvania", "United States", "www.pennmedicine.org"),
        ("nyu", "NYU Langone Tisch Hospital", "United States", "nyulangone.org"),
        ("northwestern", "Northwestern Memorial Hospital", "United States", "www.nm.org"),
        ("rush", "Rush University Medical Center", "United States", "www.rush.edu"),
        ("duke", "Duke University Hospital", "United States", "www.dukehealth.org"),
        ("vanderbilt", "Vanderbilt University Hospital", "United States", "www.vanderbilthealth.com"),
    ]
    targeted = {
        "stanford": ["https://stanfordhealthcare.org/discover/new-stanford-hospital-experience.html", "https://stanfordhealthcare.org/newsroom/news/news-updates/2019/designing-the-new-stanford-hospital-for-patients-and-caregivers.html"],
        "hopkins": ["https://www.hopkinsmedicine.org/patient-care/patients-visitors/admission-discharge/hospital-room", "https://www.hopkinsmedicine.org/news/articles/2019/06/out-with-the-old-in-with-the-modern"],
        "sunnybrook": ["https://sunnybrook.ca/patients-visitors/getting-admitted-to-hospital/room-options/"],
    }
    seeds = [{"id": hid, "hospital": name, "geography": country, "allowed_domains": [host],
              "seed_urls": targeted.get(hid, [f"https://{host}/"]), "target_candidates": 20,
              "rights_status": "unknown", "training_permission": False,
              "seed_status": "official_page_located" if hid in targeted else "proposed_seed_unvalidated",
              "hospital_attribution_verified": False,
              "note": "A named hospital seed is not acquired coverage. Shared system pages require human site attribution; never count the same system photo across hospitals."}
             for hid, name, country, host in hospital_rows]
    assert len({h["hospital"] for h in seeds}) == 50
    write_json(DATA / "hospital-images" / "hospitals.json", seeds)
    records = DATA / "hospital-images" / "records.json"
    if not records.exists():
        write_json(records, [])
    print("Created 10 official source references, 10 hypothesis pain points, and 50 named hospital seeds; acquired no images.")


if __name__ == "__main__":
    main()
