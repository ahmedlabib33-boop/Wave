# Greater Cairo street-viewer source verification — 5 November 2026

The map and street-selection provider check succeeded through the public OpenStreetMap API and Nominatim. A bounded Heliopolis map response returned **359 actual road ways** and zero mapped `man_made=surveillance` camera nodes. This is only one small on-demand map tile, not a Greater Cairo completeness claim. Both configured Overpass endpoints timed out during the check; the application records the failure, retries with backoff and preserves older records.

Public web camera checks did not yield an admissible Greater Cairo street feed:

| Provider/source | Result | Admitted to operational camera catalogue |
|---|---|---|
| [SkylineWebcams Great Pyramid](https://www.skylinewebcams.com/en/webcam/egypt/cairo/cairo/great-pyramid-of-giza.html) | The provider page rendered `OFFLINE`. | No |
| [WhatsUpCams Pyramids/Sphinx page](https://www.whatsupcams.com/en/webcams/egypt/al-qahirah/cairo/live-webcam-pyramids-giza-sphinx/) | The public page embeds a YouTube player. A server-side YouTube playback check was blocked by the network proxy, and the page is a landmark view rather than evidence of a particular street’s coverage or permission for detection. | No |
| [OpenCCTV Egypt catalogue](https://opencctv.org/cameras/egypt) | Its listed Egypt cameras were in Hurghada, Dahab and El Gouna, not Greater Cairo. | No |
| Egypt traffic/enforcement cameras | Existing source registry status remains “no documented public feed verified.” | No |

**Functioning Greater Cairo live street feeds: 0.** No street has verified camera coverage in the initial operational database. The street viewer therefore displays “no authorized, verified camera coverage” instead of claiming absence of cameras or feeds.

A source is admitted only after the existing permission record, real frame verification, explicit street/view evidence and browser-received playback evidence are present. A provider listing, OSM pin, YouTube embed, camera distance or raw Frigate camera name does not meet that bar. The actual raw request outcomes are retained locally in `research/street-viewer/` and excluded from public delivery because provider responses can change and may include third-party material.
