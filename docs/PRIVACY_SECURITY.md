# Privacy and security boundaries

This is a **local research prototype using synthetic operational data**. It is not HIPAA/PHIPA/PIPEDA certified, a clinical workflow approval, or a deployment-ready hospital security program. Public research citations and quarantined image metadata are separate from operational room state and learning artifacts. No patient data was acquired or sent to external model APIs in this implementation run.

## Implemented controls and their limits

| Area | Prototype control | Remaining production requirement |
|---|---|---|
| Access | Session/role checks in `services/app.py`; demo role selection limited to loopback | Hospital identity provider, MFA, room/unit authorization, service/device identities, access lifecycle and delegated consent |
| Sessions and browser boundary | Random session tokens, expiry, HTTP-only cookie handling, origin checks and restrictive response headers | Penetration-tested deployment, session revocation, proxy trust configuration, rate limits, complete request-body enforcement |
| Secrets | Environment configuration; no hospital credentials included | Managed secret store, key rotation, audited administration and device-bound keys |
| Transport | Local loopback development; secure-cookie/HSTS behavior available outside demo | Terminate TLS correctly, require authenticated encrypted service/device links, verify certificates and enforce egress restrictions |
| Storage | SQLite records and hash-chained events; update/delete prevention for event rows | Encryption at rest and backups, independent append-only audit sink, retention/erasure controls, restore testing and incident response |
| Sensors | Camera/microphone preference fields and UI indicators; no live hospital camera bridge | Physical sensor indicators, enforced capture control, consent lifecycle, local edge processing and operator verification |
| Dataset import | Rights evidence and human de-identification attestation, obvious-identifier rejection, image quarantine | Validated de-identification/redaction, access review, authenticated export approval and data-processing agreements |
| Learning | Research artifacts separate from operational storage, explicit review/promotion contracts | Governed research protocol and consent, measured privacy risk, validated policy/data lineage and approved lab/hospital deployment |

The local role selector is a convenience for synthetic demonstrations; it is not user identity proof. A database owner can alter triggers or rebuild an entire hash chain, so the SQLite audit is not immutable against administrators. JSON research review files are local attestations, not signed permissions. These limits must remain visible in deployment decisions.

## Data classes and handling

Public citation/aggregate metadata can be stored in the source registry, with licence and acquisition notes. Facility maps and non-identifying semantic objects still reveal sensitive operational information and require restricted access in a real facility. Patient-associated task text, room association, voice and images need stronger restrictions because apparently innocuous details can identify an individual or disclose health information.

Raw patient-room recording is off by default as a design boundary; this prototype does not ingest live audio/video into its database. Browser speech input, if enabled by a user, may rely on the browser/platform's speech service and must not be treated as local/on-prem inference. Do not use it with real patient data until the selected browser processing path and contracts are approved. Semantic events should retain only task-relevant objects and room/session references, not names, faces or diagnoses. Do not infer identity or sensitive attributes from appearance.

Downloaded research images require explicit content-specific rights before byte acquisition. They remain quarantined until automatic screening and human review pass. Missing person/OCR tools yield unknown, which blocks promotion. Automated detection and simple CSV identifier regexes are not de-identification. A photograph may contain faces, name bands, whiteboards, displays, documents or location/context identifiers that survive cropping or face blurring. Raw patient data must never enter VLA training through operational telemetry by default. See [the implemented dataset gate](DATASET_PLAN.md).

No configured retention setting alone deletes data. Before real collection, implement approved retention periods by data class, scheduled deletion of primary copies and derivatives, backup expiry, legal holds, access logs and verified deletion records. Human export approval must validate the purpose, recipients, fields, rights and destination. The image CLI's local review is a development boundary; it is not the required production export authorization service.

## Applicable legal considerations, verified against primary sources

**United States / HIPAA.** Applicability depends on the parties, information and activities. HHS describes when service providers handling protected health information act as business associates and require contractual assurances. HHS also requires appropriate role-based access to electronic PHI and administrative, physical and technical safeguards under the Security Rule. A robot software vendor should map actual data flows and subcontractors with the hospital before processing PHI. [HHS business associates](https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/business-associates/index.html), [HHS Security Rule summary](https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html).

HIPAA's minimum-necessary rule has specific exceptions, including certain treatment disclosures; it is not a blanket requirement to discard clinically necessary information. For this non-clinical application, collect only information needed for the authorized purpose. HHS describes two de-identification approaches, Expert Determination and Safe Harbor. A locally run face detector or a reviewer checkbox establishes neither approach. [HHS minimum necessary guidance](https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/minimum-necessary-requirement/index.html), [HHS de-identification guidance](https://www.hhs.gov/hipaa/for-professionals/special-topics/de-identification/index.html).

**Ontario / PHIPA.** Health information custodians need appropriate safeguards and controls on collection, use and disclosure; a supplier's obligations depend on its role and agreements. IPC guidance emphasizes preventing unauthorized access, access governance, confidentiality expectations and organizational enforcement. Device video, room/task histories and remote operator access must be part of the hospital's privacy/security assessment. Avoid assuming research reuse follows from consent for care or operational assistance. [IPC unauthorized-access guidance](https://www.ipc.on.ca/en/health-organizations/unauthorized-access), [IPC collection/use/disclosure guidance](https://www.ipc.on.ca/en/health-organizations/collection-use-and-disclosure-of-personal-health-information/disclosure).

**Canada / PIPEDA.** Do not assume PIPEDA applies uniformly to every hospital activity. The federal privacy commissioner explains that core activities of public hospitals generally fall outside PIPEDA, while non-core commercial activities and relevant commercial interprovincial/international transfers may raise federal obligations; provincial law and substantially similar legislation matter. The vendor's commercial processing may require separate analysis from the hospital's status. [OPC guidance on municipalities, universities, schools and hospitals](https://www.priv.gc.ca/en/privacy-topics/privacy-laws-in-canada/the-personal-information-protection-and-electronic-documents-act-pipeda/r_o_p/02_05_d_25/), [OPC health information jurisdiction guidance](https://www.priv.gc.ca/en/privacy-topics/health-information-genetics-biometrics/02_05_d_70_phi/).

These sources inform design review; a deployment needs institution-specific legal and privacy assessment rather than a claim of compliance from safeguards alone.

## External inference and model use

Cloud semantic/planning/critic adapters should remain disabled for patient-linked data until contractual data handling, retention, region, subprocessors and access are reviewed. Use synthetic or approved de-identified research input. Keep local/on-prem alternatives behind the same structured interfaces. Never let a model extend data access, object permission or physical authority. API retention settings and provider defaults change and require verification against the exact account/model contract before live use.

## Before an institutional pilot

Complete data-flow and threat models covering cameras, microphone, room association, operators, inference providers, integrations, software updates and support access. Establish the hospital's workflow owner, privacy officer and incident process. Validate least privilege by room/unit and role, encryption/key management, egress, backup recovery, retention/deletion, access auditing, software provenance and vulnerability response. Test privacy opt-out and sensor-state failure behavior with patients and staff in a mock room. Prove that no operational recording automatically enters a training or export job. These are release requirements, not completed checks in this prototype.
