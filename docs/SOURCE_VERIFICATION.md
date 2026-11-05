# Source verification report

Verified on 5 November 2026 UTC. Public responses and test logs are in `research/`. `docs/SOURCES.json` contains every required registry field: official documentation, endpoint/method, authentication, costs/limits, coverage, frequency, fields, accuracy, legal access, implementation status, last successful verification and blockers. A documentation-page success does not establish data access or coverage.

## Actual Cairo results

* **adsb.lol:** HTTP 200, `ac: []`, zero returned aircraft; receiver coverage unknown. The query uses 3 nautical miles and the adapter filters precisely to 5,000 m.
* **ASF:** HTTP 200; 15 intersecting GRD catalogue records stored by the application's 90-day query.
* **Copernicus:** HTTP 200; 20 intersecting metadata records stored. The 35 combined records are not 35 unique acquisitions.
* **Sensor.Community:** HTTP 200, `[]`, zero nearby stations returned.
* **TomTom:** real Cairo query without a key returned HTTP 401, “You are missing valid authentication credentials”. Adapter contract tested, geographic data availability unresolved.
* **Umbra:** correct public STAC root HTTP 200; bounded 60-document search found zero matching scenes and reported `coverage_complete=false`. Initial guessed root URLs returned 404 and were replaced by the catalogue linked from Umbra's official site. No exact-AOI coverage claim follows from this result.
* **OpenAQ:** actual location query returned HTTP 401 requiring an X-API-Key. A live measurement adapter is not implemented.
* **Overpass:** HTTP 502, server at capacity. Mapped surveillance metadata would not imply authorized stream access even if returned.
* **Government cameras:** official Egyptian traffic portal HTTP 200; no documented public El Nozha feed/API identified in the reviewed sources. No private camera was probed.
* **Public HLS test media:** HTTP 200; 1280×720 frame decoded. An isolated 90-frame inference/API run returned zero events; an official YOLOX test image independently returned a bicycle and car. No test data was written to the monitoring database.

## Reference scene revalidation

ASF returned `S1C_IW_GRDH_1SDV_20261031T155547_20261031T155612_010131_014387_BE63`. Acquisition began **2026-10-31 15:55:47 UTC**, which is **17:55:47 Africa/Cairo (UTC+02:00)** according to the timezone database. Its footprint intersects the configured AOI. Copernicus independently returned a COG representation beginning **15:55:47.910545 UTC**. These are historical October 31 acquisitions, not live surveillance. The application retains catalogue-specific identities and acquisition times instead of merging merely similar products. Full raw-product download and image-level scientific interpretation were not verified without download credentials.

## Source inventory

| Provider | Integration status | Access / coverage blocker |
|---|---|---|
| [adsb.lol](https://api.adsb.lol/docs) | Implemented and real-network tested | No endpoint-access blocker in the stated tested scope; coverage and measurement limits still apply. |
| [OpenSky Network](https://openskynetwork.github.io/opensky-api/rest.html) | Documentation reviewed; adapter not implemented | Primary ADS-B adapter uses adsb.lol; OpenSky not connected |
| [TomTom Traffic Flow](https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data) | Adapter and fixture tests implemented; keyed real-data test blocked | Cairo endpoint returned HTTP 401: You are missing valid authentication credentials |
| [Egypt Ministry of Interior traffic portal](https://traffic.moi.gov.eg/Arabic/Pages/default.aspx) | Unavailable in application | Official portal HTTP 200; no documented public camera feed/API identified in reviewed sources; this is not proof that none exists |
| [Authorized RTSP / HTTP / HLS / NVR](https://test-streams.mux.dev/) | Real HLS frame and 90-frame API pipeline tested in isolated DB; other transports need site hardware | No endpoint-access blocker in the stated tested scope; coverage and measurement limits still apply. |
| [ONVIF](https://www.onvif.org/profiles/profile-s/) | Adapter implemented; physical device not tested | No user-authorized ONVIF camera was supplied |
| [OpenCV / YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) | Real inference on official image returned bicycle and car; HLS clip returned zero events | No endpoint-access blocker in the stated tested scope; coverage and measurement limits still apply. |
| [Frigate](https://docs.frigate.video/configuration/zones/) | Documentation reviewed; raw Frigate adapter not implemented | No configured Frigate installation; MQTT worker requires normalized schema |
| [ASF DAAC Sentinel-1](https://docs.asf.alaska.edu/api/keywords/) | Implemented; real-network and application storage tested | No endpoint-access blocker in the stated tested scope; coverage and measurement limits still apply. |
| [Copernicus Data Space Sentinel-1](https://documentation.dataspace.copernicus.eu/APIs/OData.html) | Implemented and real-network tested | No endpoint-access blocker in the stated tested scope; coverage and measurement limits still apply. |
| [Umbra Open Data](https://umbra.space/open-data/) | Bounded adapter implemented and live tested; Cairo data coverage unresolved | Search truncated at 60 documents; coverage_complete=false |
| [AISstream](https://aisstream.io/documentation) | Subscriber and parsing tests implemented; keyed live connection blocked | No AISstream API key supplied; no coverage test possible |
| [Sensor.Community](https://github.com/opendata-stuttgart/meta/wiki/APIs) | Implemented and real-network tested | No endpoint-access blocker in the stated tested scope; coverage and measurement limits still apply. |
| [OpenAQ](https://docs.openaq.org/) | Researched, key blocker shown; data adapter not implemented | Actual locations request HTTP 401: A valid API key must be provided in the X-API-Key header |
| [RainViewer](https://www.rainviewer.com/api/weather-maps-api.html) | Metadata researched; no local detection/coverage adapter enabled | Cairo weather-radar coverage not established |
| [OpenStreetMap / Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API) | OSM basemap implemented; Overpass research request blocked | Overpass HTTP 502: server at capacity; no public feed can be inferred from camera tags |
| [Apple ARKit / CoreLocation / CoreMotion](https://developer.apple.com/documentation/arkit/ardepthdata) | Companion source implemented; not compiled/signed/device-tested | Linux environment lacks Xcode and a physical iPhone |
| [Apple Nearby Interaction / UWB](https://developer.apple.com/documentation/nearbyinteraction) | Researched; not implemented | No paired compatible accessory or peer supplied |
| [External radar / TI mmWave](https://dev.ti.com/tirex/explore) | Generic normalized serial/MQTT ingestion implemented; vendor parser not implemented | No radar hardware, surveyed pose or vendor-specific protocol supplied |
| [FilterPy / Stone Soup](https://filterpy.readthedocs.io/en/latest/) | Researched; cross-source association deliberately not enabled | Clock/identity/uncertainty evidence for cross-source association is absent |

## Free-first interpretation

No paid service, subscription or hardware was purchased. The official TomTom pricing page inspected at `https://docs.tomtom.com/pricing` listed 20,000 free monthly Flow Segment Data requests and 2,500 monthly incident-detail requests. Those are separate products; this build polls **Flow only** every 180 seconds (approximately 14,400 requests per 30 days before extra operations). Account eligibility, current pricing and Egypt coverage still need a valid provider key. Do not substitute outdated generic “2,500 per day” allowances. Other provider limits remain explicitly unasserted where no current numeric allowance was verified.

Public weather imagery, maps, satellite catalogues and camera location tags are not general live object detectors. The operational source registry reports runtime success separately from last acquisition and exposes missing credentials / unavailable devices rather than artificial healthy indicators.
