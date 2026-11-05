# Greater Cairo Street Viewer — incremental workstream

Before implementation on 5 November 2026: the existing project was `/workspace/nile-observer`, at commit `4f97621`. FastAPI/SQLAlchemy, React/MapLibre, all ten original pages, OpenCV/YOLOX, the mapped Frigate event adapter, source registry and 35 satellite scene records were present. **79 baseline tests passed; four opt-in network tests were skipped.** No cameras or object observations were registered.

A local Git checkpoint and private source/configuration, consistent SQLite and PostgreSQL backups were created before changes. Their safe reference is in `research/street-viewer/baseline/state.json`. The existing database, token, configuration, model and previous archives remain in place.

This workstream adds a full-screen-capable street map, actual OpenStreetMap street selection, evidence-based camera/street associations, authorized continuous video decoding, same-frame detector overlays, playback acknowledgements and provider retry diagnostics. It reuses the existing camera registry and hub. A nearby camera is not automatically a camera covering a street. Public camera listings are not stream authorization or successful playback.

OpenCV and YOLOX provide the existing decoder/detector; Frigate provides authorized NVR camera enumeration and annotated frames. The other five reviewed repositories do not provide a Cairo camera catalogue. They remain evaluated options as recorded in REPOSITORY_REVIEW.md. No private-camera scanner is introduced.

Pending original requirements and existing access blockers remain in REQUIREMENTS_STATUS.md. A functioning Cairo feed count will only include appropriately located, operator-declared live sources with recent actual playback evidence. Tests and published compatibility media are excluded from the operational catalogue.

The current external verification result is **zero functioning Greater Cairo live street feeds**; source-specific evidence and streets without recorded coverage are in `STREET_VIEWER_SOURCES.md`.

For self-hosted laptop and phone access, see `LOCAL_LAPTOP_MOBILE.md`. The app binds to loopback by default; `scripts/start-lan.sh` or `scripts/start-lan.ps1` explicitly enables LAN binding for a trusted local network.
