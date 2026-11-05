"""Build a human-readable and machine-readable source registry from recorded evidence."""

import json
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
checks = json.loads((root / "research/verification.json").read_text())
by_id = {x["id"]: x for x in checks}
for filename in ["final-source-checks.json", "followup.json"]:
    artifact = root / "research" / filename
    for item in json.loads(artifact.read_text()):
        item.setdefault("status_code", item.get("status"))
        item.setdefault("verified_at", datetime.fromtimestamp(artifact.stat().st_mtime, timezone.utc).isoformat())
        by_id[item["id"]] = item
rows = []


def add(
    provider,
    documentation_url,
    integration_method,
    authentication,
    cost_and_free_limits,
    geographic_coverage,
    update_frequency,
    observation_fields,
    accuracy_limitations,
    legal_access_conditions,
    integration_status,
    evidence_id=None,
    failure_reason=None,
    last_success=None,
):
    evidence = by_id.get(evidence_id, {})
    successful = last_success or (evidence.get("verified_at") if evidence.get("status_code") == 200 else None)
    rows.append(
        dict(
            provider=provider,
            official_documentation_url=documentation_url,
            api_endpoint_or_integration_method=integration_method,
            authentication_requirements=authentication,
            cost_and_free_tier_limits=cost_and_free_limits,
            geographic_coverage=geographic_coverage,
            update_frequency=update_frequency,
            available_observation_fields=observation_fields,
            accuracy_limitations=accuracy_limitations,
            legal_access_conditions=legal_access_conditions,
            integration_status=integration_status,
            last_successful_verification=successful,
            last_data_verification=evidence.get("verified_at")
            if evidence.get("status_code") == 200
            and evidence_id in {"adsb_cairo", "asf_cairo", "copernicus_cairo", "rainviewer"}
            else None,
            failure_reason=failure_reason,
            evidence=evidence_id,
        )
    )


add(
    "adsb.lol",
    "https://api.adsb.lol/docs",
    "GET https://api.adsb.lol/v2/point/{lat}/{lon}/{radius_nm}",
    "No key needed during test; future access policy may change",
    "Public free API; no numeric production quota asserted; provider requests contact for production use",
    "Endpoint works for Cairo; zero returned aircraft; receiver coverage not established",
    "Provider receiver-dependent; application polls every 30 seconds",
    "Position, seen_pos, clock in milliseconds, ICAO ID, callsign, altitude, track, ground speed when present",
    "Missing receivers, stale broadcasts, differing altitude datums; unknown position accuracy stays null",
    "ODbL 1.0; provider documentation and production-use conditions apply",
    "Implemented and real-network tested",
    "adsb_cairo",
)
add(
    "OpenSky Network",
    "https://openskynetwork.github.io/opensky-api/rest.html",
    "REST states API; researched as an alternative",
    "OAuth/account conditions depend on endpoint and current policy",
    "Credit-based limits; not numerically asserted here",
    "No Cairo response queried",
    "Broadcast/network dependent",
    "Aircraft state vectors",
    "Coverage and rate/account limitations",
    "Provider API terms; do not assume anonymous production access",
    "Documentation reviewed; adapter not implemented",
    evidence_id="opensky_docs",
    failure_reason="Primary ADS-B adapter uses adsb.lol; OpenSky not connected",
)
add(
    "TomTom Traffic Flow",
    "https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data",
    "GET https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/12/json?point={lat},{lon}&unit=KMPH",
    "TOMTOM_API_KEY; registration needed",
    "Official pricing snapshot lists 20,000 free monthly Flow Segment Data requests; eligibility/current quotas must be checked in account; poll 180 seconds",
    "Cairo road-segment coverage unverified without a valid key; no blanket Egypt coverage claim",
    "Provider current flow product; application polls every 180 seconds",
    "Current/free-flow segment speeds, travel times, closure, confidence, segment geometry; acquisition time not supplied",
    "Aggregate segment report is not an individual vehicle measurement; actual acquisition age unknown",
    "TomTom terms, attribution, caching and redistribution restrictions apply",
    "Adapter and fixture tests implemented; keyed real-data test blocked",
    "tomtom_docs",
    "Cairo endpoint returned HTTP 401: You are missing valid authentication credentials",
)
add(
    "Egypt Ministry of Interior traffic portal",
    "https://traffic.moi.gov.eg/Arabic/Pages/default.aspx",
    "Official portal reviewed; no public camera API/feed identified",
    "Any restricted feed requires explicit authorization",
    "No documented free enforcement-camera API verified",
    "No verified public El Nozha / Heliopolis street-camera feed",
    "Unknown",
    "No accessible live camera fields verified",
    "Portal access does not establish camera stream access",
    "No scans, credential guessing, access bypass or implied permission",
    "Unavailable in application",
    failure_reason="Official portal HTTP 200; no documented public camera feed/API identified in reviewed sources; this is not proof that none exists",
    last_success="2026-11-05T05:59:55.808550+00:00",
)
add(
    "Authorized RTSP / HTTP / HLS / NVR",
    "https://test-streams.mux.dev/",
    "Explicit server URL variable, allowlisted host, FFmpeg/OpenCV decoder; documented test https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
    "Operator-authorized URL; credentials server-side only",
    "Local open-source processing; existing authorized cameras may be free to reuse; no hardware purchased",
    "Only actual camera field of view; no Cairo test camera exists",
    "Frames depend on source; snapshots and up to 90-frame processing clips",
    "Frame pixels, bounding boxes, classes, local track IDs, reader timestamps; calibrated positions/speeds only when prerequisites hold",
    "Occlusion, model errors, ground-plane/lens errors, timestamp uncertainty; no full uncertainty guarantee",
    "Explicit authorization required; sample media is compatibility testing, not a local sensor",
    "Real HLS frame and 90-frame API pipeline tested in isolated DB; other transports need site hardware",
    last_success=json.loads((root / "research/camera-e2e.json").read_text())["captured_at"],
)
add(
    "ONVIF",
    "https://www.onvif.org/profiles/profile-s/",
    "Operator-supplied media service GetProfiles + GetStreamUri; WS-Security digest; no device discovery",
    "Authorized device credentials",
    "Open protocol; existing compatible hardware required",
    "Per authorized device; physical camera unavailable",
    "Per stream",
    "Stream URI and decodable frames",
    "Vendor/service/profile differences; no physical interoperability validation",
    "Explicit device authorization and supported profile required",
    "Adapter implemented; physical device not tested",
    "onvif",
    "No user-authorized ONVIF camera was supplied",
)
add(
    "OpenCV / YOLOX",
    "https://github.com/Megvii-BaseDetection/YOLOX",
    "ONNX nano CPU inference with object classes and per-camera IoU tracker",
    "No service key",
    "Open-source local processing; included model 3,659,407 bytes",
    "Within decodable frames only; no inferred geographic coverage",
    "Per processed frame",
    "COCO person/bicycle/car/motorcycle/bus/truck boxes and scores",
    "Domain shift, false positives, track loss; scores are not calibrated probabilities",
    "YOLOX Apache-2.0 license preserved; input imagery must be authorized",
    "Real inference on official image returned bicycle and car; HLS clip returned zero events",
    last_success=datetime.fromtimestamp(
        (root / "research/model-inference.json").stat().st_mtime, timezone.utc
    ).isoformat(),
)
add(
    "Frigate",
    "https://docs.frigate.video/configuration/zones/",
    "Separately self-hosted NVR; normalized events can enter this hub",
    "Operator-owned/authenticated deployment",
    "Open-source, hardware and model-license conditions apply",
    "Only its configured cameras",
    "Per Frigate configuration",
    "Detection/zone/speed fields depend on installation",
    "Correct scale/calibration, perspective, timing and supported version matter",
    "Frigate/code/model/video licenses and camera authorization apply",
    "Documentation reviewed; raw Frigate adapter not implemented",
    "frigate_docs",
    "No configured Frigate installation; MQTT worker requires normalized schema",
)
add(
    "ASF DAAC Sentinel-1",
    "https://docs.asf.alaska.edu/api/keywords/",
    "GET https://api.daac.asf.alaska.edu/services/search/param with platform, intersectsWith WKT, processingLevel, times and output=geojson",
    "Search worked anonymously; NASA Earthdata token/account may be required for full products",
    "Public search/data; no quota guarantee; bandwidth/storage remain local costs",
    "Real intersecting Cairo scene footprints verified",
    "Historical acquisitions; application checks every 6 hours",
    "Scene name, footprint, acquisition start/stop, platform, orbit, polarization, product type, browse, download URL, bytes",
    "Catalogue product footprint is not live object detection; no scene resolution value inferred from pixel spacing",
    "NASA Earthdata / ASF access terms and Copernicus data policy",
    "Implemented; real-network and application storage tested",
    "asf_cairo",
)
add(
    "Copernicus Data Space Sentinel-1",
    "https://documentation.dataspace.copernicus.eu/APIs/OData.html",
    "GET https://catalogue.dataspace.copernicus.eu/odata/v1/Products with collection, geometry, acquisition-time filter",
    "Metadata search anonymous during test; COPERNICUS_ACCESS_TOKEN needed for downloads",
    "Public catalogue; account/quota/download conditions apply",
    "Real GeoFootprint intersection verified for Cairo",
    "Periodic historical acquisition; polls every 6 hours",
    "Product ID/name, UTC content date, footprint, online flag, size, asset URL",
    "Not continuous surveillance; product-specific spatial resolution unverified here",
    "Copernicus data and Data Space access policies apply",
    "Implemented and real-network tested",
    "copernicus_cairo",
)
add(
    "Umbra Open Data",
    "https://umbra.space/open-data/",
    "https://umbra-open-data-catalog.s3.amazonaws.com/stac/catalog.json and linked STAC items",
    "Public catalogue worked without key",
    "Public Open Data holdings; no purchase/tasking; downloads subject to published terms",
    "60 catalogue documents checked; zero intersecting scenes found in bounded search; exact AOI coverage remains unverified",
    "Historical catalogue content; manually searched",
    "STAC geometry, acquisition time, platform, assets, per-item properties when found",
    "Bounded catalogue traversal is not an exhaustive inventory and cannot prove absence of coverage",
    "CC BY 4.0 for published Open Data; verify individual asset license and attribution",
    "Bounded adapter implemented and live tested; Cairo data coverage unresolved",
    failure_reason="Search truncated at 60 documents; coverage_complete=false",
    last_success=datetime.fromtimestamp(
        (root / "research/umbra-search.json").stat().st_mtime, timezone.utc
    ).isoformat(),
)
add(
    "AISstream",
    "https://aisstream.io/documentation",
    "wss://stream.aisstream.io/v0/stream with APIKey, AOI bounding box and position message filter",
    "AISSTREAM_API_KEY and provider registration",
    "Documented public service; current account limits must be checked; no numeric allowance claimed",
    "Cairo selected inland AOI and receiver coverage unverified",
    "Vessel transmissions/receivers; persistent subscription",
    "MMSI, position, speed/course, receiver timestamp, vessel name when returned; category may be null",
    "AIS unavailable codes rejected; receiver time differs from vessel-generated date; missing coverage is not empty water",
    "Authorized account and provider data-use conditions required",
    "Subscriber and parsing tests implemented; keyed live connection blocked",
    "aisstream_docs",
    "No AISstream API key supplied; no coverage test possible",
)
add(
    "Sensor.Community",
    "https://github.com/opendata-stuttgart/meta/wiki/APIs",
    "GET https://data.sensor.community/airrohr/v1/filter/area=30.0878597,31.3413867,5",
    "No key in tested public endpoint",
    "Public volunteer data; no guaranteed quota/SLA; poll 300 seconds",
    "Real nearby query returned [] at selected center; station coverage not assumed",
    "Station-dependent; commonly minutes; app polls every 300 seconds",
    "Station coordinates, sensor type, UTC timestamp, particulate/environmental readings",
    "Approximate station locations and volunteer sensor quality; not remote object detection",
    "Check community data license/attribution; do not reidentify private station operators",
    "Implemented and real-network tested",
    failure_reason=None,
    last_success=datetime.fromtimestamp((root / "research/live-tests.xml").stat().st_mtime, timezone.utc).isoformat(),
)
add(
    "OpenAQ",
    "https://docs.openaq.org/",
    "GET https://api.openaq.org/v3/locations?coordinates={lat},{lon}&radius=5000",
    "X-API-Key required",
    "Account/free allowance subject to current OpenAQ limits; no allowance invented",
    "Local station coverage unverified",
    "Station-dependent",
    "Potential environmental station/location and measurement fields; no data retrieved",
    "Data source quality and freshness vary; no object detections",
    "OpenAQ and originating station terms apply",
    "Researched, key blocker shown; data adapter not implemented",
    "openaq_docs",
    "Actual locations request HTTP 401: A valid API key must be provided in the X-API-Key header",
)
add(
    "RainViewer",
    "https://www.rainviewer.com/api/weather-maps-api.html",
    "GET https://api.rainviewer.com/public/weather-maps.json",
    "Public metadata request worked without key",
    "Current public API conditions apply; no unlimited-use guarantee",
    "Metadata availability does not prove Cairo weather-radar coverage",
    "Weather-product dependent",
    "Published weather tile timestamps/paths, not tracked ground objects",
    "Weather radar cannot be treated as a general object sensor; exact local coverage not verified",
    "Provider weather-data/API terms apply",
    "Metadata researched; no local detection/coverage adapter enabled",
    "rainviewer",
    "Cairo weather-radar coverage not established",
)
add(
    "OpenStreetMap / Overpass",
    "https://wiki.openstreetmap.org/wiki/Overpass_API",
    "OSM raster basemap; Overpass metadata query for mapped surveillance nodes around AOI",
    "No map key; public endpoints have service limits",
    "Public tile usage policy; no bulk/offline tile download; Overpass capacity-dependent",
    "Map rendering verified around Cairo; mapped cameras do not establish stream access",
    "Map edits, not live sensor updates",
    "Geographic road/building metadata; camera tags when mapped",
    "OSM metadata is volunteered; camera nodes are not accessible video feeds",
    "ODbL attribution; https://operations.osmfoundation.org/policies/tiles/",
    "OSM basemap implemented; Overpass research request blocked",
    "overpass_cairo",
    "Overpass HTTP 502: server at capacity; no public feed can be inferred from camera tags",
)
add(
    "Apple ARKit / CoreLocation / CoreMotion",
    "https://developer.apple.com/documentation/arkit/ardepthdata",
    "Optional SwiftUI companion with ARSession sceneDepth, CLLocationManager and CMMotionManager",
    "User camera/location/motion permission; hub token in Keychain",
    "No data-service subscription; supported iPhone and Mac/Xcode required for build",
    "Device GPS location; approximately 5 m scene depth, not 5 km detection",
    "Foreground native sensor updates; manual upload only",
    "GPS timestamp/accuracy/location; available speed/course; center depth; optional orientation",
    "No automatic depth-object identification/geolocation; GPS error varies; no physical-device validation",
    "Apple framework and permission conditions; authorized user-controlled uploads only",
    "Companion source implemented; not compiled/signed/device-tested",
    "arkit",
    "Linux environment lacks Xcode and a physical iPhone",
)
add(
    "Apple Nearby Interaction / UWB",
    "https://developer.apple.com/documentation/nearbyinteraction",
    "Supported NI session with a paired compatible peer/accessory, not passive radar",
    "Session/discovery-token exchange and compatible hardware",
    "Framework available; compatible accessories/devices required; none purchased",
    "Short-range peer/accessory-specific; no 5 km capability",
    "Session/device-dependent",
    "Relative distance/direction when actually supported",
    "No general passive object detection; session/device conditions restrict use",
    "Apple Nearby Interaction accessory/session conditions apply",
    "Researched; not implemented",
    "nearbyinteraction",
    "No paired compatible accessory or peer supplied",
)
add(
    "External radar / TI mmWave",
    "https://dev.ti.com/tirex/explore",
    "Optional explicitly configured serial/MQTT/REST normalized-JSON adapter boundary",
    "Operator-authorized device access; vendor protocol adapter needed",
    "No hardware purchased; interface code is local/open-source",
    "Entirely hardware, mounting and geometry dependent; no range claim",
    "Hardware-dependent",
    "Only fields supplied by a compatible adapter; relative measurements stay unlocated unless surveyed",
    "Binary TI/UART protocols and radar calibration are not auto-inferred",
    "Vendor SDK license and authorized hardware use apply",
    "Generic normalized serial/MQTT ingestion implemented; vendor parser not implemented",
    "radar_ti",
    "No radar hardware, surveyed pose or vendor-specific protocol supplied",
)
add(
    "FilterPy / Stone Soup",
    "https://filterpy.readthedocs.io/en/latest/",
    "Potential future statistical filters and multi-target tracking; https://stonesoup.readthedocs.io/en/latest/",
    "No hosted service key",
    "Open-source; check distribution licenses (FilterPy MIT / Stone Soup BSD)",
    "No sensor coverage of their own",
    "Input-data dependent",
    "Estimates and covariance when appropriate evidence exists",
    "Cannot establish object identity or missing measurements without inputs and assumptions",
    "Library licensing applies; no implied permission for third-party data",
    "Researched; cross-source association deliberately not enabled",
    "fusion_filterpy",
    "Clock/identity/uncertainty evidence for cross-source association is absent",
)

for row in rows:
    row["verification_scope"] = {
        "adsb.lol": "Real API access with zero returned observations",
        "ASF DAAC Sentinel-1": "Real historical metadata and footprint access",
        "Copernicus Data Space Sentinel-1": "Real historical metadata and footprint access",
        "Sensor.Community": "Real API access with zero returned observations",
        "Authorized RTSP / HTTP / HLS / NVR": "Public HLS test media, not a local camera",
        "OpenCV / YOLOX": "Real inference on a published test image",
        "Umbra Open Data": "Bounded historical metadata traversal, incomplete coverage",
        "RainViewer": "Weather metadata only, not local radar coverage",
        "OpenStreetMap / Overpass": "Basemap rendered; metadata query returned 502",
    }.get(row["provider"], "Documentation, code or an access-blocker response only; no live sensor data verified")
    if row["provider"] in [
        "Sensor.Community",
        "Authorized RTSP / HTTP / HLS / NVR",
        "OpenCV / YOLOX",
        "Umbra Open Data",
    ]:
        row["last_data_verification"] = row["last_successful_verification"]
    row["verification_time_basis"] = (
        "Recorded HTTP check time when present; local verification-artifact completion time for model, bounded Umbra and completed live-connector tests. Not a sensor acquisition timestamp."
    )

(root / "docs/SOURCES.json").write_text(
    json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": "Read-only source checks and actual runtime tests; documentation access is separate from live data access",
            "sources": rows,
        },
        ensure_ascii=False,
        indent=2,
    )
)
intro = """# Source verification report\n\nVerified on 5 November 2026 UTC. Public responses and test logs are in `research/`. `docs/SOURCES.json` contains every required registry field: official documentation, endpoint/method, authentication, costs/limits, coverage, frequency, fields, accuracy, legal access, implementation status, last successful verification and blockers. A documentation-page success does not establish data access or coverage.\n\n## Actual Cairo results\n\n* **adsb.lol:** HTTP 200, `ac: []`, zero returned aircraft; receiver coverage unknown. The query uses 3 nautical miles and the adapter filters precisely to 5,000 m.\n* **ASF:** HTTP 200; 15 intersecting GRD catalogue records stored by the application's 90-day query.\n* **Copernicus:** HTTP 200; 20 intersecting metadata records stored. The 35 combined records are not 35 unique acquisitions.\n* **Sensor.Community:** HTTP 200, `[]`, zero nearby stations returned.\n* **TomTom:** real Cairo query without a key returned HTTP 401, “You are missing valid authentication credentials”. Adapter contract tested, geographic data availability unresolved.\n* **Umbra:** correct public STAC root HTTP 200; bounded 60-document search found zero matching scenes and reported `coverage_complete=false`. Initial guessed root URLs returned 404 and were replaced by the catalogue linked from Umbra's official site. No exact-AOI coverage claim follows from this result.\n* **OpenAQ:** actual location query returned HTTP 401 requiring an X-API-Key. A live measurement adapter is not implemented.\n* **Overpass:** HTTP 502, server at capacity. Mapped surveillance metadata would not imply authorized stream access even if returned.\n* **Government cameras:** official Egyptian traffic portal HTTP 200; no documented public El Nozha feed/API identified in the reviewed sources. No private camera was probed.\n* **Public HLS test media:** HTTP 200; 1280×720 frame decoded. An isolated 90-frame inference/API run returned zero events; an official YOLOX test image independently returned a bicycle and car. No test data was written to the monitoring database.\n\n## Reference scene revalidation\n\nASF returned `S1C_IW_GRDH_1SDV_20261031T155547_20261031T155612_010131_014387_BE63`. Acquisition began **2026-10-31 15:55:47 UTC**, which is **17:55:47 Africa/Cairo (UTC+02:00)** according to the timezone database. Its footprint intersects the configured AOI. Copernicus independently returned a COG representation beginning **15:55:47.910545 UTC**. These are historical October 31 acquisitions, not live surveillance. The application retains catalogue-specific identities and acquisition times instead of merging merely similar products. Full raw-product download and image-level scientific interpretation were not verified without download credentials.\n\n## Source inventory\n\n| Provider | Integration status | Access / coverage blocker |\n|---|---|---|\n"""
for row in rows:
    intro += f"| [{row['provider']}]({row['official_documentation_url']}) | {row['integration_status']} | {row['failure_reason'] or 'No endpoint-access blocker in the stated tested scope; coverage and measurement limits still apply.'} |\n"
intro += """\n## Free-first interpretation\n\nNo paid service, subscription or hardware was purchased. The official TomTom pricing page inspected at `https://docs.tomtom.com/pricing` listed 20,000 free monthly Flow Segment Data requests and 2,500 monthly incident-detail requests. Those are separate products; this build polls **Flow only** every 180 seconds (approximately 14,400 requests per 30 days before extra operations). Account eligibility, current pricing and Egypt coverage still need a valid provider key. Do not substitute outdated generic “2,500 per day” allowances. Other provider limits remain explicitly unasserted where no current numeric allowance was verified.\n\nPublic weather imagery, maps, satellite catalogues and camera location tags are not general live object detectors. The operational source registry reports runtime success separately from last acquisition and exposes missing credentials / unavailable devices rather than artificial healthy indicators.\n"""
(root / "docs/SOURCE_VERIFICATION.md").write_text(intro)
print(f"Wrote {len(rows)} source records")
