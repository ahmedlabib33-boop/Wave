# Combined requirements ledger

Both the original multi-sensor platform and the camera/upstream investigation remain active. The continuation is additive. “Blocked” means inputs/access are missing, not that a requirement was cancelled.

| Original requirement | Current state |
|---|---|
| FastAPI modular hub, normalized origins/times/null values | Operational; original API retained; new authenticated discovery and Frigate routes added |
| SQLite, PostgreSQL/PostGIS, migrations | Operational; additive discovery migration verified on restored copies with old records unchanged |
| React/TypeScript/MapLibre PWA, monochrome, English/Arabic RTL | Operational; original ten pages retained; regional investigation added inside Live Cameras |
| Heliopolis default and 1–5 km exact radius | Preserved; Greater Cairo research bbox is separate |
| Source registry, freshness, diagnostics, history | Operational; OpenAQ polling added; inventory remains metadata-only; old evidence preserved |
| ADS-B aircraft | Existing real connector retained and live regression checked; receiver coverage still conditional |
| Road-segment speed | Existing TomTom adapter retained; actual keyed Cairo access still blocked by missing key |
| Traffic incidents / detailed road conditions | Pending adapter and keyed verification; not abandoned |
| Individual vehicle speed | Existing surveyed-calibration/validated-timestamp estimator preserved; physical metrology validation needs an authorized surveyed camera/reference |
| Authorized camera RTSP / HTTP / HLS / ONVIF / NVR | Existing tools retained; metadata → permission → real-frame check → registry integration added; physical RTSP/ONVIF hardware still needed |
| Object inference/tracking | Existing OpenCV/YOLOX/model preserved; Frigate event bridge added; latest-track/ended-track correctness improved |
| Satellite SAR search/footprints/history | Existing ASF/CDSE/Umbra modules retained; historical labels and acquisition times preserved; full credentialed products/scientific interpretation still need inputs |
| AIS vessel reports | Existing subscriber retained; live service needs a key and receiver coverage; richer static vessel metadata remains pending |
| Environmental networks | Sensor.Community retained; OpenAQ latest-reading adapter implemented from current OpenAPI; real keyed local coverage remains unverified |
| iPhone native sensor companion | Existing source retained; Xcode/signing/physical-device validation still pending; no LiDAR/UWB 5 km claim |
| REST / WebSocket / MQTT / serial / plugins | Existing channels retained; optional mapped Frigate MQTT topic added; hardware/broker-specific checks remain prerequisites |
| Fusion | Source-attributed aggregation and local-track state selection operational; cross-source identity/covariance fusion remains pending adequate evidence |
| Deployment, Windows/macOS instructions, remote-access guidance | Existing scripts/configurations retained; no new runtime dependencies required |
| Free-first and authorized inputs | Maintained; no purchases, private-camera scans, credential guesses or fabricated detections |
| Regression/preservation evidence | Baseline, private backups, Git checkpoint, record-comparison checks and new test evidence retained separately |

| Additional investigation requirement | Current state |
|---|---|
| Preserve existing project and history | Baseline checkpoint plus private configuration/SQLite/PostgreSQL backups before code changes; original commits and reports retained |
| Evaluate candidate GitHub components | Eight explicitly selected relevant projects reviewed; retain OpenCV/YOLOX and add Frigate compatibility; defer conflicting/unevaluated replacements |
| Greater Cairo investigation extent | Added as separate bounded adjustable research bbox; not asserted as an authoritative boundary or full coverage |
| Public camera discovery | Published map-metadata query implemented; actual service timeout recorded; no location tag treated as a public feed |
| Permissions, accessibility and detection suitability | Recorded separately; denied/unknown candidates cannot connect; actual decoder check required before candidate integration |
| Integrate verified authorized streams into existing hub | Same camera registration/decoder reused; real Mux compatibility-media path validated in an isolated DB, with no Cairo coordinates or detections |
| Verified Greater Cairo street feeds | Still unresolved: no documented/authorized live Cairo street feed supplied or successfully verified; none fabricated |
| No competing application | All source changes stay in the original project; disposable database copies are verification fixtures only |

The unseen second prompt's original URL list was not supplied. The reviewed eight-project set and its provenance are stated explicitly in REPOSITORY_REVIEW.md. If different repositories or an authorized Cairo feed are later supplied, they can be evaluated and admitted through these same incremental interfaces.
