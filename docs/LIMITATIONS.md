# Limits and remaining prerequisites

## What is operational

The backend, authenticated API, SQLite persistence, PostgreSQL/PostGIS deployment, real public metadata connectors, source diagnostics, map, searchable history and bilingual PWA work. Real external calls, camera decoding, positive model-image inference, validation tests, database migrations and browser tests have evidence in `research/` and VALIDATION.md. No demonstration detections are seeded.

## What this does not establish

There is **no verified free public sensor service giving complete continuous detection of all ground objects within the selected 5 km circle**. The circle is a search/filter area. The platform adds no physical long-range radar capability to an iPhone. Camera visibility, aircraft receivers, vessel receivers, environmental stations and satellite acquisitions have different coverage and timing. An empty API response does not prove absence of objects.

At verification, ADS-B and Sensor.Community returned zero local observations. Satellite metadata confirms historical coverage, including October 31, 2026; it does not confirm current road traffic or detect individual people. Catalogue records from ASF and CDSE may refer to the same physical acquisition and are not counted as independent sensors or unique passes.

## Credentials / authorized inputs needed

| Module | Remaining prerequisite | Honest status |
|---|---|---|
| TomTom Flow | Registered API key and successful Cairo query | Adapter implemented; real request without key returned 401 |
| Traffic incidents / detailed road conditions | Additional documented API adapter and key | Not implemented; closure from Flow is supported |
| AISstream | API key, receiver coverage and service acceptance | Subscriber/parser implemented; live keyed connection untested; vessel category can be null |
| Government speed cameras | Documented public feed or explicit permission | Unavailable; no access implied |
| Local IP / NVR cameras | Authorized URL, allowed host, suitable codecs | HLS compatibility verified; no Cairo camera supplied |
| ONVIF | Actual authorized device/media endpoint | Adapter implemented, physical interoperability untested |
| Individual vehicle speed | Surveyed calibration, independent validation, validated stream PTS, timing-error basis and a reference instrument | Algorithm/uncertainty components tested; real-road measurement accuracy not established |
| Full SAR products | Earthdata / CDSE credentials where required, bandwidth/storage | Search works; large authenticated downloads not validated with credentials |
| SAR scientific comparison | Calibrated, terrain-corrected, co-registered GeoTIFF inputs | Same-grid comparison works on controlled raster tests; raw SAFE preprocessing not implemented |
| Umbra Cairo imagery | Intersecting item in an adequate inventory | Bounded catalogue search tested; no exact-AOI coverage established |
| OpenAQ | API key and live measurement connector | Research only; no data adapter despite documented auth blocker |
| RainViewer | Verified local weather-radar coverage and appropriate licensed use | Metadata access only; no active sensor adapter |
| Overpass camera metadata | Available endpoint and mapped features | Research request received 502; no feed discovery from tags |
| Native iPhone sensors | Xcode/macOS, signing and physical iPhone test | Source provided; not compiled/signed/device-tested; native UI currently English |
| UWB / Bluetooth / external radar | Compatible owned/authorized hardware and protocol adapter | Generic ingestion boundaries work; pairing, vendor binary decoders and range validation not implemented |
| Acoustic localization | Defined hardware/calibration and validated experiment | Not implemented |
| Cross-sensor fusion | Identity, timing, geometry and covariance evidence | No unsupported cross-source association or fusion performed |
| Frigate | An authorized installation and event-normalization adapter | Documentation reviewed; raw Frigate events are not directly supported |

## Engineering boundaries

* SQLite spatial filtering is correct for the tested AOI but scans streamed candidates; use PostGIS for large histories. No city-scale load/soak test or automatic retention is supplied.
* Background jobs use a single API-process scheduler, not a distributed durable queue. Download status persists, but interrupted transfers require resubmission. Multiple Uvicorn workers/replicas need additional coordination.
* Camera processing handles snapshots and bounded clips with source-local IDs. No continuous cross-clip identities, recorded-video archive, low-latency HLS player, cross-camera reidentification or certified enforcement is provided.
* Independent calibration error does not cover every object-position error. Total camera location accuracy remains null. Speed uncertainty is explicitly conditional and excludes detector/association/model errors.
* Provider model scores are not guaranteed probabilities. Location/altitude datums and timestamps retain provider-specific limitations. Ground distance is not slant range.
* Live radar freshness differs by source. For TomTom, acquisition age is unknown, so only retrieval recency can be shown; historical queries by acquisition time exclude such null timestamps.
* OSM map tiles require network access and comply with the public tile policy. If unavailable, the app warns and keeps its own geographic geometry, without pretending a basemap loaded.
* The English/Arabic UI is translated with RTL layout; raw provider messages, API schemas, identifiers and evidence JSON remain in their original form. The optional native iOS UI is English source code.
* The default Cairo AOI is tested. Pole/antimeridian geometry and Web Mercator extremes are not certified. No global accuracy claim follows from this implementation.
* Authentication is a single-operator bearer token, not a multi-user authorization system. Remote operation needs HTTPS and appropriate private access. Windows and macOS startup scripts were reviewed but not executed on those platforms.
* Current free allowances and terms can change. No service is purchased or silently upgraded to a paid plan. No coverage or public camera permission is inferred from a map.
