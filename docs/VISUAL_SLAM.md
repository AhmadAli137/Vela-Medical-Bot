# Pixel-based stereo mapping and localization

`apps/web/src/stereoSlam.ts` implements a bounded stereo landmark mapping and localization prototype. It receives only synchronized left/right RGBA pixels, camera calibration and timestamps. It creates a sparse metric map, estimates subsequent camera poses against that map, reports tracking loss, and can relocalize when mapped visual features return. It is a custom implementation, not ORB-SLAM or a production navigation system.

The final interactive configuration uses 320 × 240 images, 240 features and at most 1,400 landmarks, with the accepted right-image residual included in pose verification. Its recorded phone route has a valid pose in 35 of 71 sampled post-origin observations (49.3%); median error among those valid poses is 52.01 mm. It remains a prototype with substantial tracking gaps, rather than reliable vision-guided assistance. The final results and the separate visual-pause test are detailed below.

The renderer uses measured simulator camera transforms to form the sensor images. Those transforms do not enter the estimator. Ground-truth position comparisons are calculated separately, after `slam.frame(...)`, for evaluation. Head stereo images drive the estimator; wrist camera views are separate observations. The sensor renderer also includes the room surfaces hidden by the interactive cutaway view.

## Image processing and map

Corners use the contiguous intensity segment test described by [Rosten and Drummond](https://www.edwardrosten.com/work/fast.html). Each corner receives a deterministic 128-bit patch descriptor inspired by [BRIEF](https://www.epfl.ch/labs/cvlab/research/descriptors-and-keypoints/research-detect-brief/). The implementation uses its own fixed sampling pattern; it does not include ORB's complete scale/orientation pipeline.

Rectified stereo matching compares local image patches along horizontal epipolar lines. Ambiguous matches, weak texture and failed left/right consistency checks are rejected. Accepted disparity gives depth through `z = fx * baseline / disparity`. The first accepted left camera defines the map origin, with x right, y down and z forward. Position is in metres, with scale supplied by the simulated 54 mm stereo baseline.

Persistent landmark descriptors provide correspondences in later images. Stereo point matches seed robust rigid alignment using the quaternion formulation described by [Horn](https://web.stanford.edu/class/cs273/refs/Absolute-OPT.pdf). Image reprojection minimization then refines the six-degree-of-freedom camera pose. The objective includes left-image `(u, v)` and, only when current disparity passed stereo checks, right-image `uR = uL - disparity`. Each view has robust residual weighting. The accepted right observation also participates in geometric verification and reprojection RMS; a missing right image contributes no invented residual. Geometric outliers are rejected before a pose becomes valid. New stereo landmarks are added at sufficiently separated keyframes; old mapped features can support relocalization after loss.

Default bounds are 180 detected features per frame, 700 landmarks and 400 stored trajectory samples. Initialization requires at least 18 distributed stereo features. Tracking requires at least eight geometrically consistent map correspondences; relocalization requires at least twelve with a stronger inlier ratio. Reprojection RMS must remain at or below two pixels. The first camera's origin is a coordinate definition, not a measured zero-error localization result.

## API and failure behavior

```ts
const slam = new StereoSlam({
  width: 320, height: 240,
  fx: 120, fy: 120, cx: 160, cy: 120, baselineM: 0.054,
});
slam.start();
const estimate = slam.frame({ left: leftRGBA, right: rightRGBA, timestampMs });
// Explicitly reset when starting a new scene/map:
slam.reset();
```

The images must be synchronized, rectified and top-down; timestamps must increase. `pose` is a camera-to-map transform with a position and `[qx, qy, qz, qw]` quaternion. `pose: null` means that current localization is unavailable. `lastGoodPose` and the stored path are historical information and must not be presented as a current tracked pose. Status is `initializing`, `tracking`, `lost` or `relocalized`.

Feature overlays use actual left-image corner coordinates. `tracked` indicates a geometrically accepted map correspondence; a non-null `disparity` indicates an accepted current stereo match. The confidence field is a support/reprojection heuristic, not a calibrated probability. Maps and paths contain image-derived geometry only.

Once a 3D map exists, the left image can support pose estimation against known landmarks even when new stereo depth is unavailable. This does not create new depth or replace the missing right image. A blank right image therefore prevents initialization but does not necessarily invalidate an already-supported left-image pose.

## What the prototype does not establish

- There is no bundle adjustment, optimized pose graph, loop-closure correction, inertial fusion or learned place-recognition system. Returning to a mapped view can recover a pose; it does not globally optimize accumulated map error.
- The map is sparse and bounded. It is not an occupancy map, traversability map or proof that the space between landmarks is free of obstacles.
- Small disparity from the short baseline makes distant depth uncertain. Textureless walls, repeated patterns, blur, exposure changes, large viewpoint changes and occlusions can cause loss or incorrect matches. The favorable synthetic test accuracy is not a hospital-scene accuracy guarantee.
- Rigid scene structure is assumed. Moving hands, carried objects or visible robot parts can dominate visual features and produce a plausible but wrong camera estimate. Geometric checks reduce mismatches but do not identify moving-object semantics. Correct sensor placement removes the previously observed camera-lens self-view; it does not eliminate every possible robot occlusion.
- Identical images with fresh timestamps are consistent with a stationary camera. Pixels alone cannot distinguish legitimate stationarity from replayed/frozen image content whose capture metadata falsely claims freshness.
- There is no hardware calibration, autonomous path planning, person understanding, clinical interaction or general object recognition here. Assistance motion remains explicitly scripted. Simulator contact checks and the visual observation guard have separate roles.

## Opt-in visual observation guard

`visualTrackingGuard.ts` connects observation validity to motion pausing. When enabled during active motion, it starts a timer if tracking has no valid pose, cannot initialize, or its latest frame is older than 750 ms. A continuous 1.5-second unhealthy interval latches a pause request. Healthy observations clear an unlatched timer. Recovery never clears a pause latch or resumes motion; explicit reset, new motion or manual resume starts a new guard interval.

The guard consumes only estimator status, pose validity and monotonic wall-clock capture timing. It receives no ground-truth pose. The transport sends an idempotent `pause_for_tracking` command once per latch. This is a simulation observation watchdog, not obstacle avoidance or certified robot safety.

## Reproducible checks

```powershell
node --test apps/web/tests/stereo-slam.mjs apps/web/tests/visual-tracking-guard.mjs
```

Eighteen checks passed on 2026-09-13. The estimator tests independently render textured 3D planes into stereo pixels, then compare recovered camera translation and rotation with test-only ground truth. Other cases cover unrelated/blank images, right-eye corruption, relocalization, unchanged pixels despite elapsed time, malformed input, stale timestamps and reset. A contradictory eight-pixel right-image shift preserves 173 accepted stereo patch matches but fails geometric verification against the existing map. A separate moved-left/blank-right case successfully localizes against the existing map while reporting zero fresh stereo matches. The guard tests cover loss timing, stale frames, disabled/paused motion, recovery, sticky pause state and an idempotent transport spy.

The favorable synthetic motion fixture measured approximately 1.35 mm position error and 0.00068 radians orientation error over its short combined translation/rotation sequence. Those numbers describe that fixture only. The lossless captured hospital pair in `apps/web/tests/fixtures/stereo-room/` separately checks real renderer pixels, stationary landmark tracking and corrupted-right-image rejection. It also drives a combined test where actual pixel loss requests a pause and visual recovery cannot auto-resume. That pair was captured before the sensor-only room enclosure was added; it remains a recorded stationary regression, not evidence of moving-camera accuracy in the final scene.

Measured estimator cases are recorded in [stereo-slam-tests.json](../artifacts/stereo-slam-tests.json). Moving-camera hospital evaluation uses a separate browser trace with ground truth kept outside the estimator, and reports tracking availability as well as error on valid poses.

## Recorded 320 × 240 hospital motion baseline

The local Chrome run from 2026-09-13 15:18:53–15:22:19 UTC completed the bedside approach, phone delivery, meal delivery and blinds scripted physics demonstrations. That functional pass does **not** establish accurate localization: the vision trace contains both substantial drift and extended tracking loss. This is the 320 × 240 baseline, using 180 features and a 700-landmark limit, rather than a claim about subsequent resolution experiments.

The checker recorded one pre-demo observation plus 236 observations across four separately reset maps. Each run's first observation defines the map origin and is excluded from both temporal availability and error statistics. The remaining observations are snapshots approximately every 0.75 seconds, while the camera estimator runs approximately five times per second. Availability below is therefore **sampled availability**, not a complete count of every sensor frame. Errors compare valid estimated camera positions with simulator ground truth evaluated outside the estimator; p95 uses the nearest-rank definition.

| Scripted run | Sampled temporal poses | Median / p95 / maximum error (mm) | Largest map | Relocalizations |
| --- | ---: | ---: | ---: | ---: |
| Bedside approach | 19/19, 100% | 19.95 / 49.11 / 49.11 | 512 | 0 |
| Phone delivery | 68/70, 97.1% | 312.61 / 491.23 / 495.67 | 700 | 1 |
| Meal delivery | 82/82, 100%* | 97.10 / 141.34 / 162.50 | 700 | 1 |
| Open blinds | 29/61, 47.5% | 27.56 / 151.52 / 189.51 | 700 | 1 |

*The meal run's relocalization counter increases between the 27.016 and 27.808 second observations. It therefore experienced a tracking loss and recovery between polls despite every sampled post-origin observation having a valid pose.*

Phone delivery has lost observations at 51.640 and 52.412 simulation seconds; adjacent valid observations are at 50.830 and 53.448 seconds. The blinds run has 32 consecutive lost observations from 11.194 through 37.352 seconds, with adjacent valid observations at 10.416 and 38.080 seconds. The exact loss onset and recovery are between those polls. No pose is substituted during loss, and these missing poses are excluded from error statistics rather than treated as zero error.

The largest sampled ground-truth displacement is approximately 0.80 m for bedside, 2.43 m for phone, 2.19 m for meal and 2.23 m for blinds. Phone delivery reaches approximately 0.50 m error while its status still says `tracking`; the worst sample has 15 inliers and 1.32 pixels reprojection RMS. Local reprojection consistency therefore does not establish globally accurate geometry. The blinds run's final return error of 1.85 mm must not be used to summarize its full route. Even when restricted to samples where successive ground-truth positions indicate translation above 0.01 m/s, phone delivery's median error is 328.68 mm, so stationary endpoint samples do not explain the drift.

These results do not support vision-guided placement, accurate autonomous navigation, or using the observation guard as a position-error bound. The guard can pause a missing/stale pose; it cannot detect every incorrect pose that still passes geometric checks. Assistance remains scripted independently of the estimated map. This trace does not contain ground-truth orientation, so it supplies no hospital-scene orientation-accuracy result.

The source is [assistance-check.json](../artifacts/assistance-check.json), with a source hash, all four partitions, loss intervals, translating-camera subsets and processing-time distributions in [assistance-slam-summary.json](../artifacts/assistance-slam-summary.json). Reproduce the analysis with:

```powershell
.venv/Scripts/python.exe scripts/analyze_slam_trace.py artifacts/assistance-check.json --output artifacts/assistance-slam-summary.json
```

## 640 × 480 comparison

A second local Chrome run used 640 × 480 images, `fx = fy = 240`, 240 features and a 1,400-landmark limit. It completed phone delivery and blinds motion, with the same independent evaluation method. This run has lower errors on the poses that remained valid, but the phone route lost far more tracking. The two error distributions contain different subsets of the routes and must not be interpreted as a uniform accuracy improvement.

| Scripted run | Sampled temporal poses | Median / p95 / maximum error (mm) | Largest map | Relocalizations | Median / p95 processing (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phone delivery | 40/83, 48.2% | 27.56 / 49.69 / 167.79 | 749 | 1 | 48.8 / 61.8 |
| Open blinds | 37/78, 47.4% | 11.28 / 81.32 / 90.05 | 1,400 | 2 | 59.3 / 80.8 |

Phone delivery has 43 consecutive lost observations from 22.128 through 51.944 simulation seconds; its adjacent valid polls are at 21.422 and 52.664 seconds. This omits most of the delivery motion from its valid-pose error statistics. Blinds has 41 consecutive sampled lost observations from 10.710 through 36.700 seconds, bracketed by valid polls at 10.076 and 37.346 seconds. Its relocalization counter increases inside that sampled span, proving an unobserved recovery followed by another loss; it cannot be described as one uninterrupted 26-second loss.

The estimator retains the same pixel-based reprojection thresholds and descriptor patch sizes in this experiment. At doubled resolution, those thresholds represent smaller angular errors and patches represent smaller scene regions; resolution is therefore not an isolated improvement in depth precision. Neither run establishes reliable full-route localization. Source observations and the independent summary are [vision-640-check.json](../artifacts/vision-640-check.json) and [vision-640-slam-summary.json](../artifacts/vision-640-slam-summary.json).

```powershell
.venv/Scripts/python.exe scripts/analyze_slam_trace.py artifacts/vision-640-check.json --output artifacts/vision-640-slam-summary.json
```

Both hospital baselines above precede the bounded right-image residual amendment. They remain evidence of those recorded implementations; the amendment's passing synthetic regressions alone do not establish improved hospital-route accuracy.

## Final stereo-objective configuration and browser check

The final local Chrome run, recorded on 2026-09-13 from 15:35:41 to 15:36:52 UTC, uses 320 × 240 pixels, `fx = fy = 120`, a 54 mm baseline, 240 features and a 1,400-landmark limit. Accepted right-image horizontal measurements contribute to the robust pose objective, inlier verification and reprojection RMS. This run records the phone route; it does not repeat the other three routes under the amended objective.

| Scripted run | Sampled temporal poses | Median / p95 / maximum error (mm) | Largest map | Relocalizations | Median / p95 estimator time (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phone delivery | 35/71, 49.3% | 52.01 / 136.83 / 142.88 | 484 | 2 | 13.8 / 21.2 |

The first reset-origin observation is excluded, as in the earlier comparisons. There are 36 consecutive lost observations from 22.482 through 51.734 simulation seconds, bracketed by valid observations at 21.700 and 52.530 seconds. An additional loss/recovery occurs between the 20.878 and 21.700 second polls. Valid-pose error statistics exclude these missing observations, including much of the delivery motion; the lower error maximum than the original baseline is not proof of reliable route-wide localization. Maximum sampled camera displacement is 2.42 m. Orientation accuracy remains unevaluated because the trace contains no orientation truth.

The scripted phone delivery completes with the optional visual guard disabled. The same browser check then enables the guard for a separate negative test and corrupts **only rendered camera RGBA readback**. Tracking becomes lost, the guard pauses actual simulation motion, and restoring camera pixels does not resume it. An explicit manual resume restores motion. The report records `automaticResume: false` and `manualResume: true`, with no browser errors or failed HTTP responses. This verifies the pause integration; it does not establish an error bound for poses that the estimator still accepts. Enabling the guard during a route with sustained natural tracking loss may interrupt that route.

Eighteen focused estimator/watchdog checks pass for this implementation. No bundle adjustment, optimized loop closure, autonomous route planning or vision-guided object placement is claimed. The source [final-vision-check.json](../artifacts/final-vision-check.json) and independently reproduced [final-vision-slam-summary.json](../artifacts/final-vision-slam-summary.json) preserve the functional outcomes, source hash, pose errors, unavailable observations and visual-pause result.

```powershell
.venv/Scripts/python.exe scripts/analyze_slam_trace.py artifacts/final-vision-check.json --output artifacts/final-vision-slam-summary.json
```
