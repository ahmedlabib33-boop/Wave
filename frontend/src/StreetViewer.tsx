import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapPin, Play, Search, Square, Video, X } from "lucide-react";
import { api } from "./api";
import { useT } from "./i18n";
import type { Street, StreetCamera, StreetViewerState } from "./types";
import { Action, Empty, Notice } from "./ui";

type Coverage = {
  street: Street;
  cameras: StreetCamera[];
  nearby_only: StreetCamera[];
  mapped_candidates: Array<{ id: string; name: string; distance_m: number; source_ref: string | null; permission_state: string; camera_id: string | null }>;
  coverage: string;
  coverage_complete: false;
};

function bounds(area: StreetViewerState["area"]) {
  return [[area.west, area.south], [area.east, area.north]] as [[number, number], [number, number]];
}

function LiveVideo({ camera, onClose }: { camera: StreetCamera; onClose: () => void }) {
  const t = useT();
  const [processor, setProcessor] = useState<"yolox" | "frigate">("yolox");
  const [frame, setFrame] = useState("");
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState("idle");
  const socket = useRef<WebSocket | null>(null);
  const lastMeta = useRef<Record<string, unknown> | null>(null);
  const frameCount = useRef(0);
  const shown = useRef("");
  useEffect(() => () => {
    socket.current?.close();
    if (shown.current) URL.revokeObjectURL(shown.current);
  }, []);
  async function start() {
    socket.current?.close();
    setStatus("connecting");
    setMeta(null);
    const ticket = await api<{ ticket: string; protocol: string }>(`/street-viewer/cameras/${camera.camera_id}/watch-ticket`, { method: "POST" });
    const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/street-viewer/watch/${encodeURIComponent(camera.camera_id)}`;
    const ws = new WebSocket(url, [ticket.protocol, ticket.ticket]);
    socket.current = ws;
    ws.binaryType = "arraybuffer";
    ws.onopen = () => ws.send(JSON.stringify({ processor, fps: 2 }));
    ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        const next = JSON.parse(event.data) as Record<string, unknown>;
        if (next.kind === "error") setStatus(String(next.error || "unavailable"));
        else {
          lastMeta.current = next;
          if (next.kind === "ready") setStatus("ready");
        }
        return;
      }
      const url = URL.createObjectURL(new Blob([event.data], { type: "image/jpeg" }));
      if (shown.current) URL.revokeObjectURL(shown.current);
      shown.current = url;
      setFrame(url);
      setMeta(lastMeta.current);
      setStatus("playing");
      frameCount.current += 1;
      if (frameCount.current === 1 || frameCount.current % 10 === 0)
        void api(`/street-viewer/cameras/${camera.camera_id}/rendered`, { method: "POST" }).catch(() => {});
    };
    ws.onerror = () => setStatus("unavailable");
    ws.onclose = () => setStatus((current) => (current === "playing" ? "stopped" : current));
  }
  function stop() {
    socket.current?.close();
    socket.current = null;
    setStatus("stopped");
  }
  return (
    <section className="street-video" aria-label={t("streetVideo") + " · " + camera.name}>
      <header>
        <div><Video size={17} /><strong>{camera.name}</strong></div>
        <button className="icon-button" onClick={onClose} aria-label={t("close")}><X size={18} /></button>
      </header>
      <div className="street-frame">
        {frame ? <img src={frame} alt={t("actualFrame") + " · " + camera.name} /> : <Video size={44} strokeWidth={1} />}
        {Array.isArray(meta?.detections) && <span className="detection-count">{String(meta.detections.length)} {t("detected")}</span>}
      </div>
      <div className="street-video-meta">
        <span>{status}</span><span>{String(meta?.detector || processor)}</span><span>{meta?.captured_at ? new Date(String(meta.captured_at)).toLocaleTimeString() + " UTC" : "—"}</span>
      </div>
      <div className="actions">
        <label>{t("detector")}<select value={processor} onChange={(e) => setProcessor(e.target.value as "yolox" | "frigate")} disabled={status === "playing" || status === "ready"}>
          <option value="yolox">OpenCV / YOLOX</option>
          {camera.frigate_available && <option value="frigate">Frigate</option>}
        </select></label>
        <Action run={start} disabled={status === "connecting" || status === "playing" || status === "ready"}><Play size={15}/>{t("startLive")}</Action>
        <button className="button secondary" onClick={stop} disabled={status !== "playing" && status !== "ready"}><Square size={14}/>{t("stop")}</button>
      </div>
      <p className="muted small">{t("streamEvidence")}</p>
    </section>
  );
}

function StreetMap({ state, streets, selected, choose, nearby }: { state: StreetViewerState; streets: Street[]; selected: Street | null; choose: (street: Street) => void; nearby: (latitude: number, longitude: number) => void }) {
  const t = useT();
  const target = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const latest = useRef({ choose, nearby, streets });
  const [loaded, setLoaded] = useState(false);
  latest.current = { choose, nearby, streets };
  useEffect(() => {
    if (!target.current) return;
    const instance = new maplibregl.Map({
      container: target.current, center: [(state.area.west + state.area.east) / 2, (state.area.south + state.area.north) / 2], zoom: 10.5, maxBounds: bounds(state.area), attributionControl: { compact: true },
      style: { version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap contributors" } }, layers: [{ id: "base", type: "raster", source: "osm", paint: { "raster-saturation": -1, "raster-contrast": 0.1, "raster-opacity": 0.85 } }] },
    });
    map.current = instance;
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    instance.on("load", () => {
      instance.addSource("street-lines", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      instance.addSource("selected-street", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      instance.addSource("street-cameras", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      instance.addLayer({ id: "street-lines", type: "line", source: "street-lines", paint: { "line-color": "#50575e", "line-width": 3, "line-opacity": 0.75 } });
      instance.addLayer({ id: "selected-street", type: "line", source: "selected-street", paint: { "line-color": "#fff", "line-width": 6, "line-opacity": 0.96 } });
      instance.addLayer({ id: "street-cameras", type: "circle", source: "street-cameras", paint: { "circle-radius": 7, "circle-color": "#111", "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
      instance.on("click", (event) => {
        const found = instance.queryRenderedFeatures(event.point, { layers: ["street-lines"] })[0];
        const id = found?.properties?.id;
        const street = latest.current.streets.find((row) => row.id === id);
        if (street) latest.current.choose(street);
        else latest.current.nearby(event.lngLat.lat, event.lngLat.lng);
      });
      instance.on("mouseenter", "street-lines", () => instance.getCanvas().style.cursor = "pointer");
      instance.on("mouseleave", "street-lines", () => instance.getCanvas().style.cursor = "");
      setLoaded(true);
    });
    const resize = new ResizeObserver(() => instance.resize()); resize.observe(target.current);
    return () => { resize.disconnect(); instance.remove(); map.current = null; };
  }, []);
  useEffect(() => {
    const instance = map.current; if (!loaded || !instance?.isStyleLoaded() || !instance.getSource("street-lines")) return;
    (instance.getSource("street-lines") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: streets.map((street) => ({ type: "Feature", geometry: street.geometry, properties: { id: street.id, name: street.name } })) });
    (instance.getSource("selected-street") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: selected ? [{ type: "Feature", geometry: selected.geometry, properties: {} }] : [] });
    const sites = [...state.cameras, ...state.candidates].filter((item) => item.latitude !== null && item.longitude !== null);
    (instance.getSource("street-cameras") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: sites.map((item) => ({ type: "Feature", geometry: { type: "Point", coordinates: [item.longitude!, item.latitude!] }, properties: { name: item.name } })) });
  }, [loaded, state, streets, selected]);
  return <div className="street-map"><div ref={target} className="map" data-testid="street-map" /><span className="street-map-hint"><MapPin size={14}/>{t("clickStreet")}</span></div>;
}

export default function StreetViewer() {
  const t = useT();
  const [state, setState] = useState<StreetViewerState | null>(null);
  const [streets, setStreets] = useState<Street[]>([]);
  const [selected, setSelected] = useState<Street | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [video, setVideo] = useState<StreetCamera | null>(null);
  const [coverageCamera, setCoverageCamera] = useState("");
  const [coverageEvidence, setCoverageEvidence] = useState("");
  const [liveDeclared, setLiveDeclared] = useState(false);
  async function reload() { const next = await api<StreetViewerState>("/street-viewer/state"); setState(next); setStreets((current) => current.length ? current : next.streets); }
  useEffect(() => { void reload().catch((reason) => setError(String(reason))); }, []);
  async function choose(street: Street) { setSelected(street); setVideo(null); try { setCoverage(await api<Coverage>(`/street-viewer/streets/${encodeURIComponent(street.id)}`)); setError(""); } catch (reason) { setError(String(reason)); } }
  async function search() { try { const result = await api<{ streets: Street[] }>(`/street-viewer/search?q=${encodeURIComponent(query)}`); setStreets(result.streets); if (result.streets[0]) await choose(result.streets[0]); } catch (reason) { setError(String(reason)); } }
  async function nearby(latitude: number, longitude: number) { try { const result = await api<{ streets: Street[] }>(`/street-viewer/nearby?latitude=${latitude}&longitude=${longitude}`); setStreets(result.streets); if (result.streets[0]) await choose(result.streets[0]); } catch (reason) { setError(String(reason)); } }
  if (!state) return <div className="panel padded">{error || t("loading")}</div>;
  return <div className="street-viewer">
    <Notice>{t("streetViewerNote")}</Notice>
    <div className="street-viewer-head"><div><strong>{state.functioning_live_feeds}</strong><span>{t("functioningFeeds")}</span><small>{state.count_basis}</small></div><div><strong>{state.cameras.length}</strong><span>{t("authorizedCameras")}</span><small>{t("notCoverageCensus")}</small></div></div>
    <div className="street-search"><label>{t("streetSearch")}<input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void search(); }} placeholder={t("streetSearchPlaceholder")} /></label><Action run={search}><Search size={15}/>{t("search")}</Action></div>
    <StreetMap state={state} streets={streets} selected={selected} choose={(street) => void choose(street)} nearby={(latitude, longitude) => void nearby(latitude, longitude)} />
    {!!streets.length && <section className="street-choices" aria-label={t("streetMatches")}><h2>{t("streetMatches")}</h2><div>{streets.slice(0, 30).map((street) => <button className={selected?.id === street.id ? "selected" : ""} key={street.id} onClick={() => void choose(street)}>{street.name}</button>)}</div></section>}
    {error && <p className="inline-error" role="alert">{error}</p>}
    {selected && <section className="panel padded street-results"><div className="card-top"><div><span className="eyebrow">{t("selectedStreet")}</span><h2>{selected.name}</h2><a className="text-link" href={selected.source_ref} target="_blank" rel="noreferrer">OpenStreetMap ↗</a></div><span className="badge">{coverage?.coverage || t("loading")}</span></div>
      {coverage?.cameras.length ? <div className="street-camera-grid">{coverage.cameras.map((camera) => <article className="panel" key={camera.camera_id}><h3>{camera.name}</h3><p className="muted">{camera.match_basis} · {camera.status}</p><p className="small">{camera.playback_recent ? t("recentPlayback") : t("noRecentPlayback")}</p><Action run={async () => setVideo(camera)}><Video size={15}/>{t("openViewer")}</Action></article>)}</div> : <Empty message={t("noVerifiedStreetFeed")} />}
      {!!coverage?.nearby_only.length && <Notice>{t("nearbyOnly")} {coverage.nearby_only.map((camera) => `${camera.name} (${Math.round(camera.street_distance_m || 0)} m)`).join(" · ")}</Notice>}
      {!!coverage?.mapped_candidates.length && <Notice>{t("mappedCandidates")} {coverage.mapped_candidates.map((camera) => `${camera.name} (${Math.round(camera.distance_m)} m)`).join(" · ")}</Notice>}
      {!!state.cameras.length && <details className="coverage-editor"><summary>{t("declareCoverage")}</summary><Notice>{t("coverageDeclarationNote")}</Notice><label>{t("authorizedCameras")}<select value={coverageCamera} onChange={(event) => setCoverageCamera(event.target.value)}><option value="">—</option>{state.cameras.map((camera) => <option value={camera.camera_id} key={camera.camera_id}>{camera.name}</option>)}</select></label><label>{t("coverageEvidence")}<textarea value={coverageEvidence} onChange={(event) => setCoverageEvidence(event.target.value)} rows={3}/></label><label className="check"><input type="checkbox" checked={liveDeclared} onChange={(event) => setLiveDeclared(event.target.checked)}/>{t("liveDeclared")}</label><Action run={async () => { if (!coverageCamera) throw new Error(t("authorizedCameras")); await api(`/street-viewer/cameras/${coverageCamera}/coverage`, { method: "PUT", body: JSON.stringify({ street_ids: [selected.id], evidence: coverageEvidence, live_declared: liveDeclared }) }); await reload(); await choose(selected); }}>{t("save")}</Action></details>}
    </section>}
    {video && <LiveVideo camera={video} onClose={() => setVideo(null)} />}
  </div>;
}
