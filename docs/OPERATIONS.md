# Operations

## Access and credentials

The default server binds to loopback. The Compose port is also published on loopback, not to the public internet. For iPhone access, use your own HTTPS reverse proxy or a trusted private network/tunnel with TLS. A PWA needs HTTPS for installation outside localhost; native iOS transport security also requires HTTPS. Do not expose plain HTTP or the database publicly.

Provider tokens and camera credentials belong in server environment variables or a private `.env` file with restrictive permissions. The browser holds only the hub access token in session storage. The native companion stores its access token in Keychain. This single-operator foundation has no user accounts, roles, MFA or per-device token revocation. Rotate `APP_API_KEY` and restart to revoke access. Do not treat the development setup as an internet-hardened multi-tenant service.

The service worker caches only the static application shell and same-origin assets, never API responses, source credentials, video or map tiles. Offline UI explicitly reports loss of backend access. A source outage does not become fake live detections. Source freshness and object freshness are distinct; diagnose both.

## Rate limits and capacity

Default polling: adsb.lol 30 s, Sensor.Community 300 s, ASF and CDSE 6 h, TomTom 180 s. Successful manual refreshes share the connector cooldown for the same query area; 429 responses set a bounded `Retry-After` deadline. Connection/timeouts and 5xx use limited retries with backoff. Provider contracts and quotas can change.

The verified TomTom pricing page listed **20,000 free monthly Flow Segment Data requests** at inspection. One request every 180 s is approximately 14,400 requests per 30 days before extra AOI changes/manual operations or failed attempts. No subscription is purchased by this application. Monitor the provider account; free-tier eligibility and Egyptian segment coverage require your API key and current terms. The incidents API has a separate allowance and no adapter here.

Use one Uvicorn process for this foundation: the polling scheduler and job supervision are in-process. Multiple replicas would need an external job queue/leader election. Camera processing is CPU work isolated from API request execution but sequential by default; it is not sized for a city-wide NVR. History is paginated and range-filtered; SQLite exact radius filtering streams candidates, while PostGIS first narrows them spatially. Set retention appropriate to available disk; automatic retention/deletion is not implemented.

SAR downloads default to a 2 GB job limit and persist progress at 10 MB intervals. Download redirects requiring login are reported as access blockers rather than followed into interactive authentication. Only approved provider hosts are accepted. Downloads do not automatically unpack raw SAFE products or run ESA SNAP. Georeferenced GeoTIFF uploads are limited to 200 MB and 16 million pixels. Backscatter comparison requires already radiometrically calibrated, terrain-corrected, co-registered images; preprocessing is an external prerequisite.

## MQTT

Configure `MQTT_HOST`, `MQTT_PORT`, `MQTT_TLS`, username/password and topic in `.env`; restart. Default TLS is enabled and certificate verification is not disabled. Secure and authorize the broker itself. Register an input source of type `mqtt` (or use the built-in `mqtt` ID), then publish one complete `ObservationIn` JSON object per message to the configured topic. The worker enforces matching source type, registration, timestamp/coordinate validation and a 128 KiB record limit. Raw Frigate or vendor-specific radar messages need a normalization adapter first.

## Serial hardware

Set `SERIAL_PORT` to an explicitly selected device (`COM3`, `/dev/ttyUSB0`, etc.) and `SERIAL_BAUD`. The worker reads newline-terminated normalized JSON objects, with source type `serial`. It does not probe ports or infer a vendor's binary radar protocol. Register a serial source, or use `serial`. Hardware measurements without a surveyed pose and supported geolocation remain unlocated; any relative range belongs in `details`, not in a fabricated latitude/longitude.

## Plugins and external radar

Install trusted operator-reviewed Python modules and set `SOURCE_PLUGINS`; the contract is in ARCHITECTURE.md. A TI mmWave binary parser, particular USB radar SDK, UWB accessory link, Bluetooth hardware pairing, acoustic localization and cross-sensor association are not supplied. This platform already provides the ingestion boundaries for their future adapters. Hardware range is a property of the chosen device, not of the 5 km query circle.

## Backups and migrations

Stop local writes before copying SQLite `data/observer.db` and associated data, or use SQLite's online backup API. Include the asset folders and environment configuration in encrypted/private backups. PostgreSQL deployments should use `pg_dump` plus the sensor-data volume. Never put these backups or `.env` in source control.

Alembic's initial migration creates all relational tables. The second adds PostGIS geography and a GiST index on PostgreSQL only. Installing the PostGIS extension requires a suitable database role; the included Compose image supplies it. Later autogenerated migrations must retain that conditional generated geography column deliberately. The backend automatically upgrades on startup; code and database migrations should be deployed together. No schema-destructive startup reset is performed.

## Cloud build validation

The supplied Dockerfile supports optional BuildKit CA mounts named `proxy_ca` for npm and `system_ca` for Python. Ordinary Docker builds need neither. In managed environments using an HTTPS proxy, supply the platform's public CA using BuildKit secrets and a read-only runtime CA mount, while preserving the configured proxy. Do not disable TLS verification. These environment-specific mounts are not embedded in the published image or regular Compose file.
