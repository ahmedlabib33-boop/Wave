# Final operational status

**Operational monitoring foundation**, with verified local and Docker/PostGIS execution. This is not complete physical 5 km ground-object coverage.

The default workspace serves the production app at `http://127.0.0.1:8000`; the optional Vite development server uses 5173. Read `data/access-token` locally to sign in, or configure your own `APP_API_KEY`. For a fresh installation use README.md; Docker normally serves port 8080. The archive excludes credentials, database files and installed dependencies.

At the recorded operational check (`research/operational-status.json`):

* HTTP health and frontend both returned 200.
* Center 30.0878597, 31.3413867; radius 5,000 m.
* 14 configured registry entries, including explicit missing/unavailable sources.
* 35 real ASF/CDSE historical catalogue records stored.
* **Zero stored object observations**; no fabricated or test detections seeded.

The four verified public data endpoints are adsb.lol, ASF, Copernicus and Sensor.Community. The first and last returned zero local observations. Historical Sentinel-1 coverage and the specified October 31 acquisition were verified. Umbra's bounded search did not establish exact-AOI coverage.

Traffic Flow and AIS need your registered keys. Local cameras need authorized URLs and, for physical speed, real survey/timing validation. MQTT/serial need actual configured devices/brokers. The optional native iOS companion is supplied as source and remains uncompiled and device-untested. Other unimplemented adapters and scientific limits are enumerated in LIMITATIONS.md.

Deliverables include backend/frontend source, schema/migrations, real provider adapters, source registry and verification report, camera and raster processing, authenticated ingestion, bilingual PWA, native companion source, Docker Compose, environment template, Windows/Linux/macOS startup instructions, automated tests, OpenAPI snapshot, validation report and defect log. No services or hardware were purchased and no private camera was probed.
