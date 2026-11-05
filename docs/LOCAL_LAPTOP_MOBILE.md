# Run Wave on a laptop and phone

Run the backend, map, camera decoding and YOLOX processing on the **laptop**. The phone is a responsive client; it does not need Python, Node, camera drivers, model files or provider keys.

## Laptop only

Use a terminal in the project directory:

```bash
bash scripts/start.sh
```

Then open `http://127.0.0.1:8000` on the laptop. The first start creates `data/access-token` unless `APP_API_KEY` is configured in `.env`. Enter that value at the login screen.

On Windows, double-click `scripts/start.bat` or run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

## Phone on the same Wi-Fi

1. Connect laptop and phone to the same trusted Wi-Fi network. Do not use a public or guest network.
2. Start the laptop server with LAN binding:

   ```bash
   bash scripts/start-lan.sh
   ```

   On Windows:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-lan.ps1
   ```

3. The laptop prints an address such as `http://192.168.1.20:8000`. Open **that exact address** in Safari on the iPhone, then enter the token from the laptop’s `data/access-token` file.
4. Use Safari’s Share menu → **Add to Home Screen** to install the responsive PWA shortcut.

The first mobile visit needs internet access for OpenStreetMap tiles and any configured third-party sources. It still talks to the local laptop for Wave’s API, camera video and object overlays.

If the phone cannot connect, allow inbound TCP port 8000 on the laptop **private/home network profile only**. Keep the generated token private and stop the LAN launcher when finished. The UI sends camera frames over an authenticated one-use WebSocket ticket; it never receives an RTSP/HLS/NVR URL or a provider key.

## Docker option

Docker remains localhost-only by default. To make its port reachable on the trusted LAN:

```bash
WAVE_BIND_ADDRESS=0.0.0.0 docker compose up --build
```

Open `http://LAPTOP-LAN-IP:8080` on the phone. Restore the default localhost binding by omitting `WAVE_BIND_ADDRESS` on later starts.

## Street viewer workflow

1. Select **Greater Cairo Street Viewer**.
2. Search a street, or click the map to load nearby actual OpenStreetMap street geometry and select a returned street.
3. The application shows an available player only when an authorized registered camera has an explicit street/view-coverage record. Nearby camera pins and mapped OSM surveillance sites remain marked as coverage unknown.
4. Open the live viewer. The laptop decodes actual frames. Select **OpenCV / YOLOX** for locally drawn detection boxes, or **Frigate** for a mapped authorized Frigate annotated frame. Browser receipt is recorded separately from human viewing.

The initial install has no asserted Greater Cairo feed. A camera becomes a functioning feed only after its permission, stream frame verification, street coverage evidence and recent browser playback evidence are all recorded.
