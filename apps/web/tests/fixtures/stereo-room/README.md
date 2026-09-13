These 320×240 PNGs are synchronized left/right head-camera renders captured from
the authored synthetic hospital scene in Chrome on 2026-09-13. They are pixel
fixtures, not photographs of a patient. The camera's own lens was removed from
view by correcting the optical-center placement before capture.

Calibration: fx=fy=120 pixels, cx=160, cy=120, baseline=0.054 metres. Images are
rectified, top-down RGBA after decoding. The estimator receives only these
pixels, calibration and timestamps; no simulator geometry, depth or poses.

Sources: `apps/web/artifacts/corrected-vision-head_rgb.png` and
`corrected-vision-head_stereo_right.png`. The stationary pair tests initialization,
repeat observation, corruption and a perception-driven pause latch. It does not
establish moving-camera localization accuracy; independently rendered synthetic
motion tests and separate browser motion traces cover that distinct question.
