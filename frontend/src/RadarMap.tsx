import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Area, Observation, Scene } from "./types";
import { useT } from "./i18n";

interface Props {
  area: Area;
  observations: Observation[];
  rings: GeoJSON.FeatureCollection;
  scene?: Scene | null;
  onSelect: (observation: Observation) => void;
}
export default function RadarMap({
  area,
  observations,
  rings,
  scene,
  onSelect,
}: Props) {
  const t = useT(),
    container = useRef<HTMLDivElement>(null),
    map = useRef<maplibregl.Map | null>(null);
  const latest = useRef({ observations, onSelect });
  latest.current = { observations, onSelect };
  const [loaded, setLoaded] = useState(false),
    [failed, setFailed] = useState(false),
    [idle, setIdle] = useState(false);
  useEffect(() => {
    if (!container.current) return;
    const instance = new maplibregl.Map({
      container: container.current,
      center: [area.longitude, area.latitude],
      zoom: 12.8,
      dragRotate: false,
      touchPitch: false,
      maxPitch: 0,
      attributionControl: { compact: true },
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            maxzoom: 19,
            attribution:
              '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>',
          },
        },
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": "#ddd" },
          },
          {
            id: "basemap",
            type: "raster",
            source: "osm",
            paint: {
              "raster-saturation": -1,
              "raster-contrast": 0.15,
              "raster-opacity": 0.7,
            },
          },
        ],
      },
    });
    map.current = instance;
    instance.touchZoomRotate.disableRotation();
    instance.keyboard.disableRotation();
    instance.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    instance.on("error", () => setFailed(true));
    instance.on("idle", () => setIdle(true));
    instance.on("dataloading", () => setIdle(false));
    instance.on("load", () => {
      for (const id of ["rings", "observations", "center", "scene", "roads"])
        instance.addSource(id, {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
      instance.addLayer({
        id: "scene-fill",
        type: "fill",
        source: "scene",
        paint: { "fill-color": "#222", "fill-opacity": 0.12 },
      });
      instance.addLayer({
        id: "scene-border",
        type: "line",
        source: "scene",
        paint: {
          "line-color": "#111",
          "line-width": 2,
          "line-dasharray": [4, 2],
        },
      });
      instance.addLayer({
        id: "range-rings",
        type: "line",
        source: "rings",
        paint: {
          "line-color": "#444",
          "line-width": 1,
          "line-opacity": 0.7,
          "line-dasharray": [3, 3],
        },
      });
      instance.addLayer({
        id: "roads",
        type: "line",
        source: "roads",
        paint: { "line-color": "#111", "line-width": 5, "line-opacity": 0.8 },
      });
      instance.addLayer({
        id: "center-point",
        type: "circle",
        source: "center",
        paint: {
          "circle-radius": 4,
          "circle-color": "#fff",
          "circle-stroke-color": "#111",
          "circle-stroke-width": 2,
        },
      });
      instance.addLayer({
        id: "object-points",
        type: "circle",
        source: "observations",
        paint: {
          "circle-radius": 7,
          "circle-color": "#111",
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 2,
        },
      });
      instance.on("click", "object-points", (e) => {
        const id = e.features?.[0]?.properties?.id;
        const found = latest.current.observations.find(
          (o) => o.observation_id === id,
        );
        if (found) latest.current.onSelect(found);
      });
      instance.on("mouseenter", "object-points", () => {
        instance.getCanvas().style.cursor = "pointer";
      });
      instance.on("mouseleave", "object-points", () => {
        instance.getCanvas().style.cursor = "";
      });
      setLoaded(true);
    });
    const resize = new ResizeObserver(() => instance.resize());
    resize.observe(container.current);
    return () => {
      resize.disconnect();
      instance.remove();
      map.current = null;
    };
    // Initialize once; all data and center changes are applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const instance = map.current;
    if (!loaded || !instance) return;
    (instance.getSource("rings") as maplibregl.GeoJSONSource).setData(rings);
    (instance.getSource("center") as maplibregl.GeoJSONSource).setData({
      type: "Point",
      coordinates: [area.longitude, area.latitude],
    });
    (instance.getSource("scene") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: scene
        ? [{ type: "Feature", geometry: scene.footprint, properties: {} }]
        : [],
    });
    (instance.getSource("observations") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: observations
        .filter((o) => o.latitude !== null && o.longitude !== null)
        .map((o) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: [o.longitude!, o.latitude!] },
          properties: { id: o.observation_id },
        })),
    });
    const roads: GeoJSON.Feature[] = [];
    for (const o of observations) {
      const geometry = o.details.geometry as GeoJSON.Geometry | undefined;
      if (o.object_type === "road_segment" && geometry?.type === "LineString")
        roads.push({
          type: "Feature",
          geometry,
          properties: { id: o.observation_id },
        });
    }
    (instance.getSource("roads") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: roads,
    });
  }, [loaded, area, observations, rings, scene]);
  useEffect(() => {
    if (!loaded || !map.current) return;
    const ring = rings.features.at(-1)?.geometry;
    if (ring?.type !== "Polygon") return;
    const bounds = new maplibregl.LngLatBounds();
    for (const c of ring.coordinates[0]) bounds.extend([c[0], c[1]]);
    map.current.fitBounds(bounds, { padding: 36, duration: 300 });
  }, [loaded, area.latitude, area.longitude, area.radius_m, rings]);
  return (
    <div className="map-wrap" aria-label={t("mapTitle")}>
      <div
        className="map"
        ref={container}
        data-testid="radar-map"
        data-map-ready={idle}
      />
      <div className="cardinal cardinal-east">{t("east")}</div>
      <div className="cardinal cardinal-west">{t("west")}</div>
      <div className="cardinal cardinal-south">{t("south")}</div>
      <div className="compass" aria-label={t("north")}>
        ↑ {t("north")}
      </div>
      <div className="map-coordinate" dir="ltr">
        {area.latitude.toFixed(5)}° N · {area.longitude.toFixed(5)}° E
      </div>
      {failed && (
        <div className="map-error" role="status">
          {t("mapFailed")}
        </div>
      )}
    </div>
  );
}
