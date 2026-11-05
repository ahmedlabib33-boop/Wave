# Nile Observer

**Incremental continuation:** Greater Cairo camera investigation now lives inside Live Cameras, with permission evidence, real frame checks and integration into the same hub. OpenAQ ingestion and a mapped Frigate event bridge extend the existing sources. See [current continuation status](docs/CONTINUATION_VALIDATION.md), [camera investigation](docs/GREATER_CAIRO.md), [repository comparison](docs/REPOSITORY_REVIEW.md), and the [combined requirements ledger](docs/REQUIREMENTS_STATUS.md). The original architecture, endpoints, records and dated verification reports are retained.

A working, free-first sensor hub for **30.0878597, 31.3413867**, Heliopolis / El Nozha, Cairo. Python 3.12 + FastAPI, React + TypeScript + MapLibre, SQLite or PostgreSQL/PostGIS. English and Arabic with RTL, an installable PWA, and optional native iOS companion source.

**This is an observation aggregator, not a new 5 km radar sensor.** Nothing is seeded as a live detection. Aircraft and environmental queries can legitimately return zero observations. Satellite products are historical. Cameras require explicit authorized configuration; uncalibrated detections have no object map coordinates or physical speed.

## Start on Linux / macOS

Install Python 3.12+, Node 22+ and npm, then run from this folder:

```bash
bash scripts/start.sh
```

Open **http://127.0.0.1:8000**. Read the locally generated `data/access-token` file and enter it in the app. If you configure `APP_API_KEY` in `.env`, use that value instead. Provider keys are never included in the frontend. Keep `.env` and `data/` private. All application endpoints except the minimal health check require a token; `/docs` publishes the API schema.

The script installs dependencies, creates `.env` from `.env.example`, builds the frontend, migrates the database and starts one backend worker. The included official YOLOX nano weights are optional for camera processing; their source, SHA-256 and Apache-2.0 license are in `models/`.

## Windows

Install Python 3.12 and Node 22+, then double-click `scripts/start.bat` or run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Windows and native iOS builds require testing on their respective operating systems; the Linux validation does not establish they have run there.

## Docker with PostgreSQL / PostGIS

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Open **http://127.0.0.1:8080**. To retrieve the generated token without printing it into container logs:

```bash
docker compose cp app:/app/data/access-token ./access-token.local
```

Keep that local file private and delete it after copying the token into the app. Alternatively configure a random `APP_API_KEY` of at least 24 characters in `.env`. PostgreSQL is internal to the Compose network; it has no published port. Set your own `POSTGRES_PASSWORD` in `.env` for a lasting installation. The provided default is explicitly for local development.

Health checks cover the database and application. Named volumes persist observations and downloads. `docker compose down` stops services while retaining their volumes. Do not use `down -v` if you want to keep history. See [operations](docs/OPERATIONS.md) for HTTPS, private access, backups, MQTT and serial hardware.

## What works

* Real **adsb.lol** polling, millisecond response-clock handling, position-age timestamps, knots/feet conversion, and exact WGS84 filtering from 1–5 km.
* Real **ASF** and **Copernicus Data Space** scene searches, footprint intersection, UTC acquisition times, historical browsing, provider previews, queued bounded downloads with credential blockers, and same-grid calibrated GeoTIFF change masks.
* Bounded **Umbra Open Data STAC** traversal with an explicit incomplete-coverage result.
* **TomTom Flow Segment Data** adapter, separate from individual vehicle speeds. Requires an API key; Cairo availability has not been tested with one. Unknown acquisition time remains null.
* Real **Sensor.Community** nearby station queries. No local stations were returned during verification.
* **AISstream** WebSocket subscriber behind a configured API key; AIS unavailable-value codes are handled. No keyed live verification was possible.
* Authorized **RTSP, HTTP video, HLS and ONVIF media-service** registration, time-bounded decoding in a subprocess, real YOLOX inference, conservative local tracking, independent ground-plane calibration validation and timestamp-gated physical speed estimates.
* Authenticated REST and WebSocket ingestion, optional MQTT/TLS and serial JSONL workers, source plugins, deduplication, persistent history, data freshness and failure diagnostics.
* Ten responsive PWA pages, English / Arabic, full RTL layout, honest empty states and a geographically positioned map.

[Validation evidence](docs/VALIDATION.md), [source verification](docs/SOURCE_VERIFICATION.md), [limitations](docs/LIMITATIONS.md), [defect log](docs/DEFECT_LOG.md), [architecture and contracts](docs/ARCHITECTURE.md), [camera setup](docs/CAMERAS.md), [iOS companion](ios/README.md).

## Development and tests

Run commands from the project root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[vision,sar,test]'
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 262144
```

In another terminal:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

Vite serves port 5173 and proxies HTTP / WebSocket API requests. For a production frontend, run `npm --prefix frontend run build` and restart the backend. Backend startup applies Alembic migrations idempotently. Start from the repository root; this is also the Docker working directory.

```bash
.venv/bin/pytest -q
LIVE_TESTS=1 .venv/bin/pytest backend/tests/test_live.py -q
.venv/bin/ruff check backend scripts
npm --prefix frontend run build
cd frontend
npm exec playwright -- install --with-deps chromium webkit
npm run test:e2e
```

Browser tests need a running backend and frontend, the default area and radius, and real satellite metadata previously searched/stored. **Use a disposable database/server for browser tests:** the new regional cases save an investigation area and create explicitly labeled metadata candidates. They read the generated local token or `TEST_API_TOKEN`; `UI_URL` selects that test server. The continuation validation used an isolated copy, leaving the operational database free of test candidates. The tests use an iPhone 15 Pro Max WebKit profile and desktop Chromium; this is not a physical-device certification. Network tests may fail when a public service changes or is down. Unit-test fixtures are isolated from the operational database.

`requirements.lock.txt` records the validated Python environment. `frontend/package-lock.json` pins npm dependencies. Optional extras keep geospatial raster and video dependencies separate for lightweight installations.

## License and attribution

Application code: MIT. YOLOX model: Apache-2.0, with its license preserved in `models/LICENSE-YOLOX`. Published test imagery and test streams are verification inputs, not application sensor feeds. Provider data keeps its own license: adsb.lol / OpenStreetMap ODbL; Sentinel Copernicus data policy; Umbra Open Data CC BY 4.0. Review provider conditions before redistribution or production use. See the source report for verified documentation and current access blockers.
