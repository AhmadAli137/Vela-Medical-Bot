# Hospital imagery dataset: executable acquisition and honest status

The executable corpus configuration contains **50 distinct named hospitals**, with a target of 20 candidates per hospital (**1,000 total**). This is a collection target, not a completed dataset. The bounded run acquired **9 image URL metadata records from Stanford Hospital pages, 0 image files, 0 analysis-approved images and 0 training-approved images**. All nine records remain quarantined and unreviewed. Responsive variants may refer to the same photograph; unique-content counts stay zero until byte hashing. Coverage is one candidate hospital and zero verified hospital-room images. Counts are available through `services.evidence.get_research()` and the CLI.

The source pages are Stanford Health Care's [hospital experience page](https://stanfordhealthcare.org/discover/new-stanford-hospital-experience.html) and [hospital design article](https://stanfordhealthcare.org/newsroom/news/news-updates/2019/designing-the-new-stanford-hospital-for-patients-and-caregivers.html). Their public visibility does not provide training permission. The source material includes people; no claim of privacy clearance is made. Source URLs, image URLs, timestamps and unknown rights/privacy status are preserved in `data/hospital-images/records.json`.

The same bounded run attempted official room pages for Sunnybrook and Johns Hopkins. The crawler did not proceed where robots policy could not be verified or prohibited access. `acquisition_log.json` records attempted pages and outcomes. An initial network-restricted attempt failed; a network-enabled retry yielded the nine Stanford metadata candidates. Neither robots restrictions nor authentication were bypassed.

## Run

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\acquire_images.py plan
.\.venv\Scripts\python.exe scripts\acquire_images.py status
.\.venv\Scripts\python.exe scripts\acquire_images.py crawl --hospital stanford --hospital hopkins --hospital sunnybrook --max-pages 2 --per-hospital 20 --timeout 8
```

The exact third command was run. Its successful network-enabled result was `candidate_records=9, downloaded_unique_images=0`. Running it again deduplicates hospital/image URL pairs. A full bounded discovery run uses `crawl --max-pages 30 --per-hospital 20 --max-candidates 1000`, but 47 seeds still need source-page validation before their collected images can be attributed to a particular hospital. Shared health-system pages must not be counted as independent evidence for each hospital. Seeds are not assertions of consent, access availability, room coverage or partnerships.

## Acquisition contract

The crawler permits HTTPS only, exact allowlisted hosts and public destination addresses. It rejects credentials in URLs, nonstandard ports, out-of-scope redirects, oversized bodies and image-like responses with a non-image content type. Each redirect is checked against the same domain and robots policy. It requests robots.txt before pages and images, conservatively refuses missing/unreachable/invalid robots files, respects declared crawl delays/request rates, and limits pages, candidates, response size, timeouts and redirects. It does not authenticate, use cookies to bypass access controls or execute site JavaScript. Network egress enforcement remains necessary in production; application URL checks are not a replacement for a firewall against DNS rebinding.

Metadata discovery is separate from content acquisition. `--download --permissions PATH` only downloads an image when the local permission manifest names that **exact image URL**, sets `rights_status` to `permission_verified` or `open_license_verified`, and supplies documentary `rights_evidence`. An example shape, which is not itself a permission grant:

```json
[{"image_url":"https://approved.hospital.example/room.jpg","rights_status":"permission_verified","rights_evidence":"signed-agreement-reference","commercial_reuse_allowed":false,"training_permission":false}]
```

Downloaded content must be a valid image with minimum dimension 240 pixels and at most 40 million pixels. SHA-256 filenames deduplicate identical bytes across sources while provenance records remain separate. The file is retained in `quarantine/`, with dimensions and local detection results. A proposed image record schema is in `data/schemas/image-record.schema.json`; the enforcement implementation is `services/evidence.py` and the acquisition script.

For metadata already in the registry, run `download --permissions permissions.json --record RECORD_ID`; this rechecks robots and permission before acquiring bytes. The `crawl --download` option applies to newly discovered records. Neither command changes review or promotion status.

## Privacy and human review

`scan` optionally uses locally installed OpenCV HOG person detection and Tesseract OCR (`opencv-python`, `pytesseract` plus the Tesseract executable). These optional detectors are **not installed or validated in this run**. Missing detectors return `unknown`, never `clear`. OCR text is not retained. No image is sent to a cloud model. Person detection may miss seated/occluded people; OCR may miss names, charts, labels and screens. A clear automatic scan is not de-identification.

Promotion requires verified content/hash, explicit rights, recognized room type, accepted quality, both detector statuses `clear`, a named human reviewer, timestamp, and `human_reviewed_clear` privacy status. Unknown/flagged scans block promotion even if a reviewer is named. This prototype supplies detection and quarantine; it does not implement a validated redaction model. Redacted derivatives require their own hash, permission record and review.

```powershell
.\.venv\Scripts\python.exe scripts\acquire_images.py scan
.\.venv\Scripts\python.exe scripts\acquire_images.py review --record RECORD_ID --review review.json
```

`review.json` contains `human_reviewer`, `privacy_status`, `room_type`, and `quality`. It cannot rewrite hashes, detector findings or rights. Training promotion additionally requires separate `training_permission=true` and `commercial_reuse_allowed=true`, and the `--training` flag. Local review identities are attestations, not cryptographically verified signatures; production needs authenticated review workflows and tamper-resistant storage.

## From collection to usable priors

Review each hospital's source terms and actual image relevance before scaling. Balance single/shared rooms, acute/general wards, age-appropriate non-patient mock rooms, lighting, clutter and furniture. Preserve geography, named facility and collection date. Split train/evaluation by hospital and near-duplicate image groups to prevent leakage; byte deduplication alone does not detect crops or alternate resolutions. Do not infer exact mass, friction, attachment, calibration or metric geometry from photographs. A single photograph can support multiple uncertain scene hypotheses, not calibrated hardware authorization. The current quarantine has no approved input for real-to-sim analysis.

No raw patient operational imagery flows into this corpus or into policy training automatically. Prospective hospital collection needs site governance, rights/consent, approved retention, privacy review and a deletion process before acquisition.
