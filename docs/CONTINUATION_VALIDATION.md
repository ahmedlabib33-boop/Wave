# Continuation validation — 5 November 2026

The original platform was extended in place. Its application architecture, ten pages, original endpoint set, model, configuration, history and previously published verification evidence remain available. This report supersedes **implementation status only** where older dated baseline reports said OpenAQ or raw Frigate events were not implemented; those reports have not been erased or rewritten.

## Checkpoint and preservation

* Git baseline: `1d6a772768bd7da964b72fa4e6696f6e85fa8985`; local checkpoint `checkpoint/pre-continuation-20261105`. The two original commits remain in history.
* Private pre-change archive, consistent online SQLite snapshot and PostgreSQL custom-format dump: `/workspace/private-backups/20261105T063654Z`. This private folder contains configuration and must not be published.
* Original delivery archive `/workspace/nile-observer.zip` is retained. Packaging now refuses to overwrite an existing delivery; use `--output` for a new archive.
* Baseline: **59 passed**, four opt-in network tests skipped; frontend build and Ruff passed; running application/frontend HTTP 200.
* Baseline SQLite: 35 scene records, 14 sources, one radar setting, zero observations/cameras/downloads. The production configuration file is unchanged.
* Additive migration `3_discovery` creates only `camera_candidates` and `discovery_runs`. Existing table structures and old migrations are not replaced.
* All original records were checked on the restored SQLite copy. A restored PostgreSQL/PostGIS copy also retained every row of all six original application tables, including its 15 scene records, after the new migration.
* **45 original model/evidence files checked: all unchanged.** This includes the previous validation/source reports and original raw verification results. The YOLOX weight SHA-256 remains `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`.

Evidence: `research/continuation/baseline/`, `preservation-check.json`, `postgres-preservation.txt`, and `evidence-preservation.json`. Disposable database copies were test fixtures using the same application source, not a replacement app. They were used so UI/stream test candidates never contaminated the operational database.

## Incremental additions

1. Separate Greater Cairo investigation bbox and public map camera inventory, inside Live Cameras.
2. Permission evidence, strict server URL references, bounded real frame checks, configuration fingerprints, audit runs and idempotent integration into the existing camera registry.
3. Existing OpenCV/YOLOX retained; authorized Frigate REST/MQTT event bridge added without trusting unverified upstream geography or speed.
4. OpenAQ v3 locations/latest connector added through the existing source registry, with key gating and real acquisition-time/coordinate validation.
5. Latest source-local track selection moved before geographical/class filtering; ended tracks remain historical. This prevents old positions from reappearing as live after a track ended or moved outside the radius. No unsupported cross-source identity fusion was added.
6. Eight explicitly selected upstream repositories reviewed with pinned references, license metadata, actual compatibility findings and adoption/defer decisions.

See GREATER_CAIRO.md, REPOSITORY_REVIEW.md and REQUIREMENTS_STATUS.md for scope and remaining requirements from both prompts.

## Executed regression checks

| Check | Result | Evidence |
|---|---|---|
| All original + new backend tests | **79 passed**, four external tests skipped by offline default | `backend-regression-final.txt` / `.xml` |
| Real public connectors, run separately | **4 passed**: adsb.lol, ASF, CDSE, Sensor.Community | `live-connectors.txt` / `.xml` |
| Python checks | Passed | `lint-final.txt` |
| TypeScript/Vite production build | Passed | `frontend-build-nav-fix.txt` |
| Desktop Chromium + iPhone 15 Pro Max WebKit | **14 passed** | `regression-repaired/browser.txt`, JSON and screenshots |
| Original API path set | All original paths present | `live-verification.json`; new schema saved separately as `docs/openapi-continuation.json` |
| Heliopolis center, 5,000 m radius and scene records | Preserved in migration/integration checks | `live-verification.json`, `preservation-check.json` |
| PostgreSQL/PostGIS restored-backup migration | All old tables' records unchanged; new tables empty; revision `3_discovery` | `postgres-preservation.txt` |
| Published authorized HLS compatibility media | Real 1280×720 frame decoded and linked to the existing registry in an isolated DB; no object coordinates or detections created | `live-verification.json` |
| Greater Cairo live metadata request | Read timeout; exposed as unavailable, not zero cameras | `live-verification.json`, `discovery-research.json` |
| Upstream repository review | Eight metadata/commit/documentation reviews; no bulk replacement/install | `repository-review.json`, `upstream/file-checks.json` |
| Extracted delivery smoke check | Packaged source imported; new database migrated; frontend/health returned 200; 15 sources and zero seeded object observations; private-file/known-credential checks passed | `package-smoke.txt` |

Paths in this table are under `research/continuation/` unless stated otherwise. Physical iPhone, live keyed OpenAQ/TomTom/AIS, a user-supplied Cairo camera, actual Frigate broker/NVR and physical ONVIF/radar hardware remain unverified. The native companion source was preserved; this Linux session does not provide an Xcode/device build.

## New failure cases covered

Unknown/denied permission produces **no stream connection**; undocumented candidates never become detections; invalid/documentation URLs with credentials are rejected; metadata upserts preserve permission and previous links; failed inventory requests preserve candidates; repeated integration does not create duplicate cameras; a changed URL or permission invalidates a check; revocation preserves records while disabling the source; a permission change during decode cannot produce a verified stream; disabled/unmapped Frigate cameras are rejected; false-positive events are skipped; acquisition times are retained; unsupported coordinates/speeds stay null; ended/out-of-area tracks do not revive earlier live positions; mobile station coordinates are not invented.

## Defects found and repaired during this continuation

| Before | Repair | After |
|---|---|---|
| Initial new discovery JSX had an unclosed callback expression | Corrected before publication; formatted and type-checked | Production build passed |
| A lazy source page requested an old asset while the verification output folder was being rebuilt | Sequence build before tests and retain previously served hashed assets with `emptyOutDir: false`; use a separate verification build directory | The original application build stays available; full browser rerun passed |
| iPhone rapid Arabic navigation could reopen the menu before the previous hash event arrived, then unexpectedly close it | Track already-applied navigation and ignore its redundant hash event; preserve actual Back/Forward handling | All original navigation/language cases and new regional cases passed in both engines |
| Optional OpenAQ source previously had no adapter and raw Frigate events were unsupported | Added schema-verified OpenAQ parsing and an explicitly mapped/authenticated Frigate bridge | New tests pass; actual keyed/device prerequisites remain clearly blocked |

The two failed intermediate browser runs are retained separately under `regression/` and `regression-final/`. The successful repaired run is under `regression-repaired/`; failures were not hidden by removing tests, forced clicks or raising their timeouts. Browser traces may contain access tokens and are excluded from Git and delivery archives.

## Honest operational limits

No Greater Cairo street feed was successfully verified or integrated, and no private/government camera was scanned. The real Mux check is compatibility media with no Cairo location. No complete 5 km ground-object coverage is implied by the radar range rings or regional metadata scope. Original pending hardware/access/scientific requirements remain active in REQUIREMENTS_STATUS.md.

## Operational reload

The original service was gracefully stopped and reloaded with the additive migration, using its existing database and access token. A second consistent private SQLite backup was made immediately before reload. Previously served frontend asset files were retained. The restarted service returns HTTP 200 for the frontend, health, settings, sources, scenes and discovery endpoints. All **35 original scene records** and all original source IDs remain present; the Heliopolis center and 5,000 m radius are unchanged. It now has 15 sources, zero cameras, zero object observations and zero camera investigation candidates/runs. Test-media and browser fixtures were confined to disposable databases. See `research/continuation/operational-check.json` and `rollout-checkpoint.json`.
