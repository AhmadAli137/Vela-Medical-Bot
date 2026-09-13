# Evidence service and opportunity hypotheses

The working service reads **10 official-source references and 10 normalized, paraphrased opportunity hypotheses** from `data/source-registry/sources.json` and `data/patient-feedback/painpoints.json`. It ranks hypotheses, exports provenance and dataset status through `services.evidence.get_research()`, and supports authorized CSV normalization. It contains **zero raw patient comments** and no imported respondent-level survey data. These are contextual evidence references plus engineering judgments, not a reanalysis of surveys.

Sources were checked on September 12, 2026. Newer source releases supersede date assumptions in the supplied product document. The supplied Markdown summaries are project evidence, not proof that this implementation reviewed the absent original hardware handout or videos.

## What the public evidence supports

| Source | Grounded use | Limits and access |
|---|---|---|
| [CQC Adult Inpatient Survey, current 2025 release](https://www.cqc.org.uk/publications/surveys/adult-inpatient-survey) | Communication, inpatient experience and discharge context | Official indexed results were available; direct fetch returned 403. No raw report or comments scraped. |
| [CMS HCAHPS](https://www.cms.gov/medicare/quality/initiatives/hospital-quality-initiative/hcahps-patients-perspectives-care-survey) | Standardized experience domains including responsiveness, environment, communication and discharge | Measures experience, not the prevalence of phone-retrieval requests or robot impact. Public aggregates do not grant access to identifiable comments. |
| [CIHI patient experience resources](https://www.cihi.ca/en/patient-experience) and [data availability FAQ](https://www.cihi.ca/en/patient-experience/patient-reported-experience-measures-prems-frequently-asked-questions) | Canadian inpatient survey framework | Historical CPERS data before March 2024 can be requested through CIHI; none requested or acquired. |
| [Care Opinion API and licence](https://www.careopinion.org.uk/info/api) | Possible narrative source after authorization | Published feedback uses CC BY-NC-SA 4.0; commercial use needs a commercial licence. No stories copied. |
| [Ontario Patient Ombudsman 2024/25](https://patientombudsman.ca/Publications/Annual-Highlights/2024-25) | Complaint-informed health-care experience context | Complaints are selected reports, not population prevalence or robot efficacy evidence. |
| [NHS Staff Survey 2025](https://www.nhsstaffsurveys.com/results/national-results/) | Staff experience and workload context; aggregate results are downloadable | Publisher reports over 760,000 respondents; this is not an exact denominator or count of non-clinical interruptions. |
| [AHRQ SOPS Hospital Database](https://www.ahrq.gov/sops/databases/hospital/index.html) | Staffing/work pace, handoffs and safety-culture domains | Aggregate reports do not identify how many minutes a robot can save; respondent-level data require a separate pathway. |
| [CFNU 2026 Member Survey](https://nursesunions.ca/research/2026-cfnu-member-survey-summary-report/) | Canadian nursing work-life context | Publisher says nearly 5,000 nurses; member survey sampling must be examined before extrapolation. |
| [CMA Physician Health Survey reports](https://www.cma.ca/physician-wellness-hub/resources/national-physician-health-survey-reports) | Physician wellbeing and administrative burden context | Much of this burden has a software/workflow solution and is assigned zero direct embodiment value. |
| [Johns Hopkins hospital-room guidance](https://www.hopkinsmedicine.org/patient-care/patients-visitors/admission-discharge/hospital-room) | Institutional room, cleaning and medical-alarm context | Object/workflow context, not pain-point prevalence; medical alarms remain outside robot control. |

No source in this seed corpus directly validates autonomous bedside manipulation, clinical benefit, reduced falls, improved survey scores, or staff time savings. The strongest directly supported themes are communication, responsiveness, environment and staff workload. Mapping those themes to phone retrieval, readiness checks or room reset is explicitly an **inference** requiring observation and patient/staff co-design.

## Ranking that does not manufacture survey measurements

Each normalized record preserves the requested pain-point fields, provenance, citations, a proposed intervention, required modalities, risks and scenario link. `original_text_if_licensed` and `estimated_staff_minutes_saved` are null. Frequency, severity and frustration scores also remain null because those measures were not derived from source data. Numerical staff/workflow/embodiment/feasibility scores are 0–5 product hypotheses under `score_basis=product_hypothesis_not_survey_measurement`.

The deterministic versioned heuristic is:

```text
benefit = 1.5 * patient_autonomy_gain + staff_time_signal
          + workflow_disruption_signal + robot_solvability
penalty = 2 * clinical_risk + regulatory_complexity + crowded_market_penalty
opportunity_score = max(0, benefit - penalty) * embodiment_value / 5
```

A zero-embodiment problem scores zero even when important. The implementation rejects non-finite/out-of-range scores and time-savings numbers without a measurement source. The formula does not grant autonomy, validate a skill or infer efficacy. Unknown values are conservatively zero in the score and remain null in the record. This first version does not weight a numerical evidence-quality score because its sources supply indirect context, not measured intervention outcomes.

The three highest-ranked implemented hypotheses are personal-item reach, room readiness checks and clear-zone observation. Informational status and physician paperwork are scored down on embodiment. Equipment search receives a market-crowding penalty. These priorities can change after representative interviews, direct time-and-motion observations and controlled comparisons against a bedside organizer, accessible controls, RTLS and existing staff workflows.

## Authorized local CSV ingestion

```powershell
.\.venv\Scripts\python.exe scripts\ingest_feedback.py approved-feedback.csv --source authorized-source.json --output data\patient-feedback\reviewed-import.json --privacy-attestation human_reviewed_deidentified --intended-use research
```

Required CSV content is `normalized_summary`; `stakeholder`, `theme`, `subtheme` and `original_text_if_licensed` are optional. The source JSON must identify `id`, `url`, verified rights status and documentary rights evidence. Commercial use requires an explicit commercial grant; verbatim comments require `raw_comments_reuse_allowed=true`. No seed source currently authorizes raw import. Source and human privacy attestations are mandatory; obvious email/phone/patient-ID patterns cause refusal. Pattern checks cannot establish de-identification, so manual review remains required. The script writes a separate artifact and does not publish it or merge it into the curated service corpus automatically.

Importing and ranking are local deterministic operations. There is no automatic source crawler for feedback or external model call. Future model-assisted coding should output the same structured schema, maintain citations and uncertainty, and undergo human review without broadening reuse rights.

## Verification

`tests/test_evidence.py` checks ranking, non-finite scores, fabricated savings, CSV rights/commercial/verbatim boundaries, identifier rejection, robots failures, URL scope, metadata quarantine, image permissions, byte-hash deduplication and separate training promotion. The successful run reported **25 passed**. Test images/comments are explicitly synthetic fixtures and are excluded from acquired dataset counts.
