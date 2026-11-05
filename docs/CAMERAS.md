# Authorized camera and speed setup

No network scans, guessed credentials, automatic device discovery or government enforcement feeds are included.

1. Set a server-only URL variable in `.env`, for example `CAMERA_DRIVEWAY_URL`, containing a stream you own or are explicitly authorized to use. Credentials may be in that URL; the application stores only the variable's name. Restart after changing environment configuration.
2. Add the exact camera or NVR hostname/IP to `CAMERA_ALLOWED_HOSTS`. This is an operator allowlist, not a subnet scan. Trust the allowed server's HLS manifests and redirects: the FFmpeg decoder is not a network sandbox for nested media references. Use a dedicated restricted network for cameras.
3. In Live Cameras, register a name, variable name, protocol and acknowledgement. Supply geographic position/direction/FOV only if known. Camera coordinates do not become object coordinates.
4. Load a frame to test decoding. Register no coordinates for public test media. A documented public compatibility test is `https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8` (Mux test stream). This is sample media, **not Cairo monitoring**, and must never be presented as local observations.
5. Use Detect and track clip for real inference. The included official YOLOX nano ONNX model is Apache-2.0; provenance and SHA-256 are in `models/manifest.json`. It detects COCO person/bicycle/car/motorcycle/bus/truck classes. Scores are model confidence values, not calibrated probabilities of correctness.

RTSP / rtsps and authorized NVR channels use the operator-provided stream URL. HTTP video and HLS use FFmpeg-supported codecs. ONVIF uses an explicitly supplied **media-service endpoint**, `GetProfiles` and `GetStreamUri` with WS-Security UsernameToken digest and Basic Auth. Returned stream hosts must also be allowlisted. ONVIF transport/authentication and different camera codecs require device-specific testing; no physical ONVIF camera was available.

Frames are read in a time-bounded subprocess. The worker suppresses decoder stderr to prevent FFmpeg from logging credentialed URLs. A hung reader is terminated; other sources continue. Camera viewing is an on-demand authenticated snapshot interface, not a low-latency video player or an NVR archive. `CAMERA_PROCESSING_ENABLED=true` runs registered cameras sequentially in repeated bounded clips. Each processing session has distinct local track IDs; identity is not preserved across clips or cameras. Continuous multi-camera high-throughput processing needs a dedicated worker service.

## Calibration

The calibration API accepts at least four non-collinear lens-corrected image points and their surveyed ground-plane east/north coordinates in metres, image dimensions, WGS84 survey origin, survey error, notes, and **separate independent validation points** inside the calibration polygon. Do not paste synthetic test coordinates into a real camera calibration.

It rejects singular geometry, points outside the image, independent points outside the calibrated hull, and independent residual error above `max(1 m, 3 × stated survey error)`. Points outside the calibrated polygon are not extrapolated. If the stream resolution changes, the saved calibration is not applied. Ground projection uses the bottom center of the detector box, which is an approximation to ground contact and may fail under occlusion, slopes, lens errors or camera movement.

`camera_ground_projection` explicitly labels geographic positions inferred from the calibrated ground plane. Total `location_accuracy_m` remains null because detector footpoint and scene-model errors are not quantified. The separate calibration residual is retained; it is not misrepresented as complete object-location accuracy.

## Speed

Physical speed is emitted only when all of the following hold:

* Valid independent calibration and a point within its ground polygon.
* A source-local tracked object with at least two ground positions.
* Explicit operator `pts_validated=true` and a nonzero `timestamp_error_s`.
* Strictly increasing finite stream PTS throughout the processed clip; elapsed time 0.2–5 s; speed at most 100 m/s as a plausibility gate.

`speed_mps = ground_displacement_m / elapsed_pts_seconds`; km/h multiplies by 3.6. The result is a displacement-average speed over that interval, not a certified instantaneous speed. The reported **conditional** 95% error component propagates survey/calibration and stated timing errors only. It explicitly excludes detector footpoint error, track swaps, occlusion and model bias; complete measurement uncertainty remains unknown. This number is not a certification or accuracy guarantee. Numeric model confidence is kept separate.

Frigate can be run separately for a dedicated camera deployment. Its current zone/speed documentation was reviewed. A native Frigate event adapter and certified traffic enforcement pipeline are not included; transform authorized Frigate events into this hub's normalized contract before ingestion. The MQTT worker accepts normalized observations, not raw Frigate event JSON.

## Validation performed

`scripts/check_video.py` decoded the public HLS stream at 1280×720. `scripts/check_video_processing.py` ran 90 frames through registration, decoding, inference and event handling in a **temporary isolated database**; it returned zero detector events in that clip. A separate official YOLOX test image produced real car and bicycle boxes (`research/model-inference.json`). No test media, test coordinates or test detections were inserted in the operational database. Real-road speed accuracy still requires a surveyed authorized camera and an independent reference instrument.
