# Reference-based scene upgrade

Checked 12 September 2026 (Toronto; acquisition timestamps are UTC). This upgrade has two downloaded real hospital-room photographs for local architectural inspection and nine downloaded CC0 material maps. The new Bracket Bot handout is now available and visually inspected. No verified public CAD, URDF, exact kinematic definition, or current hardware SDK for that robot revision was obtained.

## Robot evidence and fidelity limits

The direct source is the user-supplied `C:/Users/Ahmad/Downloads/Bracket Bot Handout.pdf`, inspected as [page 1](../artifacts/references/handout-page-1.png) and [page 2](../artifacts/references/handout-page-2.png). The three supplied demonstration videos are additional visual references; a video demonstrates visible behavior without establishing calibrated geometry, torque limits, interface semantics, or repeatability.

The first handout page labels a stereo depth head, independent shoulder vertical lift, dual 7-DOF arms, wrist cameras, rotary pinch grippers, two hub-motor drive wheels, and a tall central mast. Its silhouette has white rounded covers, exposed dark joint/rack regions, a black pill-shaped stereo face, and mint-green gripper pads. These are usable observations for a visual reconstruction. The brochure states 2 kg payload per arm, floor-to-6-ft reach, Jetson Orin Nano Super 8 GB, 8.5 Nm hub motors, and 50 kg cm gripper stall servo torque. These remain manufacturer brochure claims rather than independently measured limits. In particular, servo stall torque is not a validated safe gripping-force limit.

The second page describes SLAM/navigation, speaker/microphone, custom IK with Meta Quest teleoperation, demonstration collection, VLA training/deployment, and shared 8x H100 compute. It does not supply a joint-axis table, link transforms, masses/inertias, joint limits, collision meshes, actuator mapping, firmware protocol, or a tested SDK contract. The two shoulder lifts are labeled separately from the dual 7-DOF arms; the handout does not settle whether each lift is included in that degree-of-freedom count.

The PDF's embedded links lead to demonstration videos, a kit application form, and an email address. It contains no CAD or SDK download link. No contact message was sent.

| Public-source check | Result and interpretation |
| --- | --- |
| [Bracket-Bot-Inc organization](https://github.com/Bracket-Bot-Inc) | The visible current public organization listing does not establish a downloadable new dual-arm hardware model. |
| [BracketBotOS API metadata](https://api.github.com/repos/Bracket-Bot-Inc/BracketBotOS), [BracketBotAI](https://api.github.com/repos/Bracket-Bot-Inc/BracketBotAI), [BracketBotApps](https://api.github.com/repos/Bracket-Bot-Inc/BracketBotApps) | Each unauthenticated live metadata request returned HTTP 404. This means unavailable through that public endpoint; it does not distinguish private, renamed, or deleted repositories. Exact checks are preserved in [the audit JSON](../assets/provenance/bracketbot-public-audit.json). |
| Indexed historical repository pages and [legacy quickstart](https://docs.bracket.bot/docs/quickstart-setup-integration-branch) | Historical/cached material and BracketBotCapstone references are not evidence that the new handout robot has the same hardware or API. They were not substituted for a current SDK. |
| Manufacturer site access | `bracket.bot` and `docs.bracket.bot` could not be retrieved in this research session. `bracketbot.com` did not expose a usable download in the inspected page. Inaccessibility does not prove no model exists. |

A model built from these sources can truthfully be described as a handout/video-informed visual and kinematic approximation. Accurate hardware actuation remains dependent on revision-matched CAD/URDF, joint axes and limits, calibrated zero positions, actuator IDs, verified feedback/control interfaces, and acceptance against the physical robot. Attractive rendering or a successful synthetic grasp does not validate those properties.

## Inspected real hospital-room references

These public photographs were fetched with exact-domain HTTPS restrictions, public-address checks, size bounds, and successful robots checks. They are retained only as the user's local visual references. No open license or training/redistribution permission was established. They have not been added to the hospital image training corpus, approved as de-identified data, or granted public-application rights. Publish only the original source links and the separately licensed scene materials; keep these cached photographs out of public static routes and distribution bundles.

| Official source and local file | Directly visible architectural cues |
| --- | --- |
| [Stanford Health Care: Designing the New Stanford Hospital for Patients and Caregivers](https://stanfordhealthcare.org/newsroom/news/news-updates/2019/designing-the-new-stanford-hospital-for-patients-and-caregivers.html), June 2019. [Local photograph](../assets/references/stanford-patient-room-reference.jpg), 1024 x 683, 95,677 bytes. | Large daylight window; grey family sleeper couch; central bridge table; warm wood wall panels; clinical service rail/monitor arm; pale walls; wood-look floor; ceiling grid and lift strap. The bed is outside this composition. |
| [Ronald Reagan UCLA Medical Center photo gallery, Patient Room](https://www.uclahealth.org/hospitals/reagan/about-medical-center/photo-gallery). [Local photograph](../assets/references/ucla-patient-room-reference.jpg), 2492 x 3329, 847,403 bytes. | Full hospital bed with caster chassis, raised backrest, quilt and pillow; overbed table; service rails and outlets; pale blue headwall; ceiling curtain track and two-tone privacy curtain; blue sleeper couch and recliner; mottled resilient floor; acoustic ceiling and luminous panels. |

Both were visually inspected and show no visible people or obvious patient identifiers. Small equipment/product labels and printed material remain present, and this limited inspection is not formal privacy clearance. Room dimensions, accessibility clearances, fixture specifications, and material composition cannot be reliably measured from these photographs. The scene can use these observations for authored geometry and lighting, without claiming to be a surveyed digital twin of either hospital.

The complete image URLs, download timestamps, hashes, local-only rights status, and visual-inspection observations are in [hospital-reference-images.json](../assets/provenance/hospital-reference-images.json). Total local photograph content: **2 files, 943,080 bytes**. These are separate from the earlier candidate-metadata research corpus.

## Reusable material files

The following assets were obtained through the [official Poly Haven API](https://polyhaven.com/our-api) using an identifying User-Agent, then downloaded from the file URLs returned by the API. All nine file MD5 hashes match the provider manifests; local SHA-256 hashes and dimensions are also recorded. Poly Haven licenses its actual texture assets under [CC0](https://polyhaven.com/license); that permission does not automatically extend to its website prose, logos, or example renders.

| Material | Local directory | Intended visual use |
| --- | --- | --- |
| [Oak Veneer 01](https://polyhaven.com/a/oak_veneer_01) | `assets/textures/oak_veneer_01/` | Warm wood headwall, casework, furniture. |
| [Linoleum Brown](https://polyhaven.com/a/linoleum_brown) | `assets/textures/linoleum_brown/` | Fine mottled resilient-floor appearance. This asset is linoleum, not verified vinyl; use as an acknowledged visual proxy. |
| [Rough Linen](https://polyhaven.com/a/rough_linen) | `assets/textures/rough_linen/` | Pale-blue woven curtain or upholstery; optional authored tint for bedding. |

Each directory contains `*_diff_1k.jpg`, `*_nor_gl_1k.jpg`, and `*_rough_1k.jpg`. Read the diffuse map as sRGB and the OpenGL normal/roughness maps as linear data. Set tiling and normal strength according to the scene's authored scale. Optical roughness and visual material appearance provide no measured friction, infection-control, fire-rating, durability, or clinical suitability evidence.

**Acquired: 3 materials, 9 JPEG maps, 6,686,020 bytes.** All three diffuse maps were inspected. No generated texture is presented as a hospital photograph. [pbr-materials.json](../assets/provenance/pbr-materials.json) records artist credits, CC0 source links, channel paths, API file manifests, and checksums. Credits are retained even though the asset license does not require them. These files can be bundled with the scene under the stated CC0 terms.

This asset acquisition establishes available visual inputs. The simulator's implementation and its final visual/actuation validation are tracked separately; this document does not claim photorealism, calibrated dynamics, real-robot execution, or clinical efficacy.
