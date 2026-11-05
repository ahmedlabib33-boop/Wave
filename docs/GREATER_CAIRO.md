# Greater Cairo investigation in the existing application

This extends **Live Cameras** and the existing sensor registry. It creates no replacement application or second sensor hub. The radar overview, its Heliopolis center and its 1–5 km radius retain their existing meaning.

## Separate geographic scope

Expand “Greater Cairo camera investigation” in Live Cameras. Its initial research rectangle is south **29.75**, west **30.90**, north **30.35**, east **31.75** in WGS84. This is an engineering search extent, **not an authoritative Greater Cairo administrative boundary, exhaustive urban footprint or sensor-coverage claim**. The rectangle is adjustable within bounded regional limits.

The investigation setting uses a separate `app_config` record. Saving it does not change the active radar center, radius, existing camera locations, satellite records or observation history. Camera candidates can be recorded without coordinates. Only actual object measurements with valid coordinates enter the radar map; candidate sites do not become object detections.

## Public metadata search

The fixed, documented Overpass API is queried for mapped `man_made=surveillance` features. Results are capped at 200 and the query timeout is 20 seconds; the client has a 30-second bound. A successful same-area result is cached for ten minutes; rate-limit responses set a cooldown. The service can fail or be at capacity.

Only camera-site tags, map reference URLs and coordinates/centers returned by the catalogue are retained. Stream URL tags are neither copied nor followed. An OSM site may be private, inaccurate, old or unrelated to a publicly accessible stream. Neither a map tag nor a reachable image establishes permission to monitor or run object detection.

The actual Greater Cairo check in this continuation timed out. An earlier GET attempt returned HTTP 406. The application reports the failed check and preserves existing candidates; it does not convert a failed response into “zero cameras” or “complete coverage.” No authorized Greater Cairo street-camera feed was verified, so none was fabricated or registered.

`OVERPASS_ENDPOINT` defaults to `https://overpass-api.de/api/interpreter`. An explicitly configured supported public community endpoint can be selected; the application does not scan arbitrary hosts or try to discover private cameras. Public service availability and usage policy apply.

## Authorization and stream verification

1. Record a documented candidate or inspect a returned map record. Public documentation references must not contain credentials or signed access keys.
2. Record either documented public permission or owner authorization, the applicable viewing/detection conditions, and an explicit operator acknowledgement. These are **operator declarations**, not automated legal or ownership verification.
3. Configure the actual stream URL in a server variable such as `CAMERA_SITE_URL`. Add its exact host to the existing `CAMERA_ALLOWED_HOSTS`; do not put passwords or credentialed URLs in permission notes.
4. Bind the variable name and protocol to the candidate. No network connection is attempted while permission is unknown or denied.
5. Run the authorized frame check. It reuses the existing isolated decoder and timeout behavior. Success means a frame was decoded, not that object inference, geographical calibration or complete coverage was validated.
6. Integrate a successfully checked permitted stream into the existing camera/source registry. The check must be less than 24 hours old and still match the server URL fingerprint. Repeated integration returns the existing link rather than creating another camera.

Changing a bound permission record invalidates its check and disables an already linked source until the operator verifies/re-enables it deliberately. Permission revocation never deletes historical observations or cameras. A permission or URL change during a frame check prevents that check from being accepted. Changing the stream after verification requires another check. Source credentials and their URL fingerprint are not returned by the candidate API.

Mapped coordinates describe the camera site, not a detected object's position. Registration does not create calibration or infer a range/FOV. The existing independent survey, projection and timing requirements still gate object geography and speed. Unknown fields stay null.

## Append-only investigation evidence

The additive migration creates `camera_candidates` and `discovery_runs`. It alters none of the original application tables. Candidate rows retain permission/configuration/link state across repeated inventory queries. Every permission record, stream check, inventory attempt and first integration has an audit entry. Inventory audit entries retain the parsed metadata returned by that query, including partial-search status and provider remarks. Failed queries keep previous candidates and their verification evidence.

New authenticated routes:

* `GET/PUT /api/discovery/area`
* `GET/POST /api/discovery/candidates`
* `POST /api/discovery/search`
* `PUT /api/discovery/candidates/{id}/permission`
* `POST /api/discovery/candidates/{id}/verify`
* `POST /api/discovery/candidates/{id}/integrate`
* `GET /api/discovery/runs`

The existing `/api/cameras`, calibration, processing, source-health, history and map endpoints remain available. There is no new endpoint for probing arbitrary URLs or IP ranges.

## Frigate compatibility without a second app

The existing OpenCV/YOLOX path remains intact. Authorized Frigate deployments can now send documented `new`, `update` and `end` events through **`POST /api/integrations/frigate`**, authenticated with the existing hub token. Alternatively set an exact `FRIGATE_MQTT_TOPIC` on the configured authorized MQTT broker.

`FRIGATE_CAMERA_MAP` is a server JSON object mapping upstream names to **already authorized registered local camera IDs**. For example, map your actual Frigate camera name to the camera ID returned by this hub's registry. Unmapped, absent or disabled cameras are rejected. This is explicit source association, not cross-camera identity inference.

The normalizer preserves upstream frame time, object ID, label, pixel bounding box, model score, event lifecycle and raw evidence. It skips events explicitly marked false positives. It does **not** accept arbitrary upstream coordinates or speed as validated physical measurements: this bridge keeps them null because calibration/unit/uncertainty equivalence has not been established. Such optional raw fields remain evidence rather than becoming measurements.

Ended tracks remain searchable history and do not appear as current live tracks. Latest state is chosen by source-local identity before radius and class filters, preventing an older in-area point from reappearing after its latest position moved outside. Different sources' IDs are never automatically merged. PostgreSQL still uses its spatial index for historical queries; live filtering scans the bounded recent window so spatial prefiltering cannot revive an older track state.

No Frigate installation, camera credentials or broker was supplied for live NVR testing. Protocol normalization, authorization, timestamp preservation, unknown physical fields, duplicate messages and lifecycle behavior are covered by isolated tests. A published Mux HLS test stream separately passed a **real** candidate frame-check/integration exercise in a disposable database, with no Cairo coordinates or detector events created.

## OpenAQ continuation

The previously researched OpenAQ source now has a v3 `locations` / `locations/{id}/latest` adapter using the provider's published OpenAPI fields. It checks at most three locations and 50 readings per location, with exact WGS84 radius validation after a small over-query margin. Known acquisition time, parameter, value, provider and license metadata are retained. A mobile station's missing current coordinates do not become its last known site position. Values lacking a valid measurement time are skipped.

Set `OPENAQ_API_KEY` only on the backend. Polling defaults to 900 seconds and remains blocked when the key is missing. This is environmental station data, not object detection. The schema and normalization tests pass; a keyed Cairo data/coverage check remains unavailable. The previous documentation's “adapter not implemented” status is a preserved baseline and is superseded by this continuation report.
