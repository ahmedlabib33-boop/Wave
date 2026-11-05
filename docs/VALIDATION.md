# Validation report

Validated in the managed Linux workspace on **5 November 2026 UTC**, with Python 3.12 and Node 24. Results apply to the stated inputs and environment, not to unconfigured sensors or city-wide physical detection coverage.

## Executed checks

| Check | Result | Evidence |
|---|---|---|
| Backend unit / API / integration regression suite | **59 passed**, four opt-in external tests skipped in the offline run | `research/tests-final.txt`, `tests-final.xml` |
| Four real public-provider tests, opt-in executed separately | **4 passed**: adsb.lol, ASF, Copernicus, Sensor.Community | `research/live-tests.txt`, `live-tests.xml` |
| React / TypeScript production build | Passed; lazy map/page bundles and no build warnings | `research/build-final.txt` |
| Python static checks | Passed | `research/lint-final.txt` |
| Extracted delivery archive | Fresh SQLite migration, backend health, built frontend, default radius and empty observation store all pass from extracted files | `research/package-smoke.txt` |
| Desktop Chromium + iPhone 15 Pro Max WebKit | **10 browser tests passed** against both Vite and the built production server | `research/browser-final.txt`, `browser-production.txt`, screenshots |
| SQLite migration upgrade / downgrade / upgrade | Passed on a clean temporary database | Versioned migrations and repeated API test startup |
| PostgreSQL 16 / PostGIS 3.5 migration roundtrip | Passed; generated geography column exists; head `2_postgis` | `research/postgis-migrations.txt` |
| Docker image / Compose application | Built and started as a non-root process; app and DB health checked; frontend, API and real ASF retrieval exercised | `research/docker-build-final.log`, `compose-e2e.txt` |
| Authorized HLS snapshot | Decoded one real 1280×720 frame | `research/camera-e2e.json` |
| Authorized HLS registration → detector → ingestion API pipeline | 90 frames processed in isolated temporary DB; zero events; no fabricated positions/speeds | `research/camera-processing-e2e.json` |
| Official YOLOX image inference | Real bicycle and car predictions; model SHA-256 recorded | `research/model-inference.json`, `models/manifest.json` |
| Umbra bounded live catalogue search | 60 documents, zero matching scenes, explicitly truncated/incomplete | `research/umbra-search.json` |
| Reference October 31 Sentinel-1C acquisition | Verified through ASF and independently corroborated by CDSE metadata | `research/asf_reference.json`, `copernicus_cairo.json`, SOURCE_VERIFICATION.md |

The default backend test run skips external tests to make offline tests reproducible. The separate live run **did execute all four**. Fixtures, test images, synthetic raster matrices and isolated test databases are not operational sensor detections.

One dependency warning remains: the installed Starlette TestClient announces a future HTTP client migration. It does not fail the tests or affect the running provider client. The locked environment records the actual tested versions.

## Acceptance criteria

| Requirement | Outcome |
|---|---|
| Application starts | Passed on local SQLite and Docker/PostGIS |
| Default Cairo coordinates load | Passed: 30.0878597, 31.3413867, 5,000 m |
| Radius 1–5 km | All five radii checked with ellipsoidal boundary cases; UI persistence tested at endpoints |
| Map renders | Real OSM tiles, geodesic range rings and north-up compass verified in Chromium and WebKit; screenshots inspected |
| Genuine external connector | Four real connectors passed, including successful metadata storage in the running app |
| Traffic integration | Flow adapter and normalization tests pass; actual Cairo request returned 401 without a key, blocker retained |
| Satellite scene search | ASF and CDSE return real intersecting metadata; 35 source-specific records stored locally |
| Authorized test stream | Mux's published test media decoded and processed in an isolated hub; no Cairo association |
| Missing sources unavailable | Credentials, government feeds and absent devices shown explicitly; zero-result responses remain distinct |
| Historical data distinguished | Scene metadata has separate storage/page and historical labels, not live radar markers |
| No fabricated distances | Horizontal WGS84 geodesics tested against known geodesic constructions; unlocated observations stay unlocated |
| Source timestamps | UTC acquisition values preserved; provider omissions remain null; provider clock units tested |
| iPhone UI | iPhone 15 Pro Max WebKit profile, mobile navigation, no body overflow; physical-device test still needed |
| English / Arabic | All ten pages and RTL switching tested; numeric display isolation added for mixed-direction values |
| Automated tests run | Unit/API, external and browser suites executed; before/after regression failure evidence retained |
| Accurate implementation status | SOURCE_VERIFICATION, SOURCES.json, LIMITATIONS, CAMERA and iOS documents distinguish code, live data and unavailable hardware |

## Failure behavior exercised

Invalid/out-of-range/nonfinite coordinates; one-sided coordinate pairs; absent, timezone-less and future timestamps; invalid speeds/headings/confidence; duplicate events; stale observations; source-local track behavior; exact radius filtering; recentering; missing/disabled source rejection; provider 429 backoff; one provider failing while another succeeds; unknown acquisition times; malformed WebSocket messages; invalid source plugins; invalid camera authorization; missing camera URLs; degenerate or independently inaccurate calibration; out-of-hull ground points; unvalidated/zero/negative frame time intervals; invalid AIS unavailable codes; bad rasters; raster path traversal; unauthenticated HTTP and WebSocket access; atomic ingestion rollback.

Camera speed tests use a controlled surveyed-plane fixture with known metre displacement and elapsed time. They verify the formula and gating; **they do not establish real-road metrological accuracy**. SAR raster tests use controlled registered GeoTIFF arrays, not a claim of identified changes in Cairo. No NASA/CDSE large-product download with credentials, physical ONVIF/serial/radar device, live keyed AIS/TomTom service, Windows/macOS runtime, Xcode build or physical iPhone was available to validate.

## Browser environment notes

Desktop Chromium launched directly. WebKit initially lacked shared libraries and the managed user could not run the privileged dependency installer. Public Debian libraries were extracted into the user-owned Playwright runtime. The actual WebKit engine then passed all five mobile cases. Host-requirement preflight was bypassed only because the dependencies were installed in that isolated runtime; actual browser launch and rendering were not bypassed or mocked. Normal developer machines can use `playwright install --with-deps`.

Repeated Docker builds on the managed VFS driver exhausted workspace disk during final packaging. Unused build cache was cleared and the build/browser checks repeated. No user sensor database or persistent observation was deleted to recover space.
