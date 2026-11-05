import { useEffect, useState } from "react";
import { Camera as CameraIcon } from "lucide-react";
import { api, fileURL } from "./api";
import { useT } from "./i18n";
import type { Camera } from "./types";
import { Action, Empty, Notice } from "./ui";
import CameraDiscovery from "./CameraDiscovery";

function CameraCard({
  camera,
  reload,
}: {
  camera: Camera;
  reload: () => Promise<void>;
}) {
  const t = useT(),
    [frame, setFrame] = useState(""),
    [calibration, setCalibration] = useState(""),
    [result, setResult] = useState("");
  useEffect(
    () => () => {
      if (frame) URL.revokeObjectURL(frame);
    },
    [frame],
  );
  return (
    <article className="panel camera-card">
      <div className="card-top">
        <h3>{camera.name}</h3>
        <span className="badge">{camera.protocol.toUpperCase()}</span>
      </div>
      <div className="camera-image">
        {frame ? (
          <img src={frame} alt={camera.name} />
        ) : (
          <CameraIcon size={38} strokeWidth={1} />
        )}
      </div>
      <p className="mono small">
        {camera.latitude === null
          ? "—"
          : `${camera.latitude}, ${camera.longitude}`}
      </p>
      <p className="muted">
        {t(camera.calibration ? "hasCalibration" : "noCalibration")}
      </p>
      <div className="actions">
        <Action
          secondary
          run={async () =>
            setFrame(await fileURL(`/cameras/${camera.id}/frame`))
          }
        >
          {t("frame")}
        </Action>
        <Action
          run={async () => {
            const r = await api(`/cameras/${camera.id}/process`, {
              method: "POST",
            });
            setResult(JSON.stringify(r, null, 2));
            await reload();
          }}
        >
          {t("process")}
        </Action>
      </div>
      <details>
        <summary>{t("calibration")}</summary>
        <Notice>{t("calibrationNote")}</Notice>
        <label>
          {t("calibrationJSON")}
          <textarea
            value={calibration}
            onChange={(e) => setCalibration(e.target.value)}
            dir="ltr"
            rows={10}
            placeholder={'{"image_points": [...], "ground_points_m": [...]}'}
          />
        </label>
        <Action
          secondary
          run={async () => {
            await api(`/cameras/${camera.id}/calibration`, {
              method: "PUT",
              body: JSON.stringify(JSON.parse(calibration)),
            });
            await reload();
          }}
        >
          {t("applyCalibration")}
        </Action>
      </details>
      {result && <pre dir="ltr">{result}</pre>}
    </article>
  );
}
export default function Cameras() {
  const t = useT(),
    [cameras, setCameras] = useState<Camera[]>([]),
    [error, setError] = useState("");
  async function reload() {
    try {
      setCameras(await api("/cameras"));
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    void reload();
  }, []);
  const [name, setName] = useState(""),
    [urlEnv, setUrlEnv] = useState("CAMERA_MAIN_URL"),
    [protocol, setProtocol] = useState("rtsp"),
    [lat, setLat] = useState(""),
    [lon, setLon] = useState(""),
    [direction, setDirection] = useState(""),
    [fov, setFov] = useState(""),
    [authorized, setAuthorized] = useState(false);
  return (
    <>
      <Notice>{t("cameraNote")}</Notice>
      <CameraDiscovery onIntegrated={reload} />
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <details className="panel registration">
        <summary>{t("addCamera")}</summary>
        <div className="form-grid">
          <label>
            {t("name")}
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </label>
          <label>
            {t("urlEnv")}
            <input
              dir="ltr"
              value={urlEnv}
              onChange={(e) => setUrlEnv(e.target.value)}
            />
          </label>
          <label>
            {t("protocol")}
            <select
              value={protocol}
              onChange={(e) => setProtocol(e.target.value)}
            >
              {["rtsp", "http", "hls", "onvif"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            {t("latitude")}
            <input
              type="number"
              step="any"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
            />
          </label>
          <label>
            {t("longitude")}
            <input
              type="number"
              step="any"
              value={lon}
              onChange={(e) => setLon(e.target.value)}
            />
          </label>
          <label>
            {t("direction")}
            <input
              type="number"
              min="0"
              max="359.99"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            />
          </label>
          <label>
            {t("fov")}
            <input
              type="number"
              min="0.1"
              max="360"
              value={fov}
              onChange={(e) => setFov(e.target.value)}
            />
          </label>
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={authorized}
            onChange={(e) => setAuthorized(e.target.checked)}
          />
          {t("authorized")}
        </label>
        <Action
          run={async () => {
            if (!authorized) throw new Error(t("authorized"));
            await api("/cameras", {
              method: "POST",
              body: JSON.stringify({
                name,
                url_env: urlEnv,
                protocol,
                latitude: lat === "" ? null : Number(lat),
                longitude: lon === "" ? null : Number(lon),
                direction_deg: direction === "" ? null : Number(direction),
                fov_deg: fov === "" ? null : Number(fov),
                authorized,
              }),
            });
            await reload();
            setName("");
          }}
        >
          {t("saveCamera")}
        </Action>
        <Notice>{t("onvifHelp")}</Notice>
      </details>
      <div className="camera-grid">
        {cameras.map((c) => (
          <CameraCard key={c.id} camera={c} reload={reload} />
        ))}
      </div>
      {!cameras.length && <Empty message={t("cameraEmpty")} />}
    </>
  );
}
