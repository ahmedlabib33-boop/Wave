import { useEffect, useState } from "react";
import { api, fileURL } from "./api";
import { date, number, useT } from "./i18n";
import type { Area, Scene } from "./types";
import RadarMap from "./RadarMap";
import { Action, Empty, Notice } from "./ui";

async function saveFile(path: string, name: string) {
  const url = await fileURL(path);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
function Comparison() {
  const t = useT(),
    [before, setBefore] = useState<File | null>(null),
    [after, setAfter] = useState<File | null>(null),
    [units, setUnits] = useState("db"),
    [threshold, setThreshold] = useState(3),
    [confirmed, setConfirmed] = useState(false),
    [result, setResult] = useState<Record<string, unknown> | null>(null);
  return (
    <details className="panel registration">
      <summary>{t("compare")}</summary>
      <Notice>{t("compareNote")}</Notice>
      <div className="form-grid">
        <label>
          {t("before")}
          <input
            type="file"
            accept=".tif,.tiff"
            onChange={(e) => setBefore(e.target.files?.[0] || null)}
          />
        </label>
        <label>
          {t("after")}
          <input
            type="file"
            accept=".tif,.tiff"
            onChange={(e) => setAfter(e.target.files?.[0] || null)}
          />
        </label>
        <label>
          {t("units")}
          <select value={units} onChange={(e) => setUnits(e.target.value)}>
            {["db", "linear_power", "amplitude"].map((s) => (
              <option key={s} value={s}>
                {t(s)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("threshold")}
          <input
            type="number"
            min="0.1"
            max="40"
            step="0.1"
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
          />
        </label>
      </div>
      <label className="check">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        {t("calibrated")}
      </label>
      <Action
        run={async () => {
          if (!before || !after || !confirmed) throw new Error(t("calibrated"));
          const ids: string[] = [];
          for (const file of [before, after]) {
            const form = new FormData();
            form.append("file", file);
            const uploaded = await api<{ raster_id: string }>(
              "/satellite/rasters",
              { method: "POST", body: form },
            );
            ids.push(uploaded.raster_id);
          }
          setResult(
            await api("/satellite/compare", {
              method: "POST",
              body: JSON.stringify({
                before_id: ids[0],
                after_id: ids[1],
                units,
                threshold_db: threshold,
                radiometrically_calibrated: true,
                co_registered_and_terrain_corrected: true,
              }),
            }),
          );
        }}
      >
        {t("compareRun")}
      </Action>
      {result && (
        <>
          <pre dir="ltr">{JSON.stringify(result, null, 2)}</pre>
          <Action
            secondary
            run={() =>
              saveFile(
                "/satellite/rasters/" + result.raster_id,
                "change-mask.tif",
              )
            }
          >
            {t("getRaster")}
          </Action>
        </>
      )}
    </details>
  );
}
interface Job {
  id: string;
  scene_id: string;
  status: string;
  bytes_received: number;
  error: string | null;
}
export default function Satellite({
  scenes,
  area,
  rings,
  reload,
}: {
  scenes: Scene[];
  area: Area;
  rings: GeoJSON.FeatureCollection;
  reload: () => Promise<void>;
}) {
  const t = useT(),
    [provider, setProvider] = useState("asf"),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [selected, setSelected] = useState<Scene | null>(null),
    [preview, setPreview] = useState(""),
    [incomplete, setIncomplete] = useState(false),
    [jobs, setJobs] = useState<Job[]>([]);
  async function getJobs() {
    setJobs(await api("/downloads"));
  }
  useEffect(() => {
    void getJobs().catch(() => {});
    const id = setInterval(() => {
      void getJobs().catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    setPreview("");
  }, [selected?.id]);
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );
  return (
    <>
      <Notice>{t("satelliteNote")}</Notice>
      <div className="panel search-bar">
        <label>
          {t("provider")}
          <select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value);
              setStart("");
              setEnd("");
            }}
          >
            <option value="asf">ASF Sentinel-1</option>
            <option value="copernicus">Copernicus</option>
            <option value="umbra">Umbra Open Data</option>
          </select>
        </label>
        <label>
          {t("start")}
          <input
            type="datetime-local"
            disabled={provider !== "asf"}
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          {t("end")}
          <input
            type="datetime-local"
            disabled={provider !== "asf"}
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
        <Action
          run={async () => {
            const result = await api<{ truncated?: boolean }>(
              "/scenes/search",
              {
                method: "POST",
                body: JSON.stringify({
                  provider,
                  start: start ? start + "Z" : null,
                  end: end ? end + "Z" : null,
                }),
              },
            );
            setIncomplete(Boolean(result.truncated));
            await reload();
          }}
        >
          {t("searchScenes")}
        </Action>
      </div>
      {incomplete && <Notice>{t("searchIncomplete")}</Notice>}
      <div className="satellite-layout">
        <section className="panel scene-list">
          <header className="panel-header">
            <h2>{t("historicalScenes")}</h2>
            <span>{scenes.length}</span>
          </header>
          {scenes.length ? (
            scenes.map((s) => (
              <button
                className={
                  "scene-row " + (selected?.id === s.id ? "selected" : "")
                }
                key={s.id}
                onClick={() => setSelected(s)}
              >
                <span className="badge">
                  {t("historical")} · {s.source_id}
                </span>
                <strong className="break mono">{s.name}</strong>
                <span>{date(s.acquired_at)}</span>
                <small>
                  {s.platform} · {s.product_type}
                </small>
              </button>
            ))
          ) : (
            <Empty message={t("noScenes")} />
          )}
        </section>
        <section className="panel">
          <header className="panel-header">
            <h2>{t("footprint")}</h2>
            <span className="eyebrow">WGS84</span>
          </header>
          <RadarMap
            area={area}
            observations={[]}
            rings={rings}
            scene={selected}
            onSelect={() => {}}
          />
          {selected && (
            <div className="scene-detail">
              <dl className="detail-grid">
                <div>
                  <dt>{t("acquisition")}</dt>
                  <dd>{date(selected.acquired_at)}</dd>
                </div>
                <div>
                  <dt>{t("resolution")}</dt>
                  <dd>{number(selected.resolution_m, "m")}</dd>
                </div>
              </dl>
              <div className="actions">
                {selected.preview_url && (
                  <Action
                    secondary
                    run={async () =>
                      setPreview(
                        await fileURL(
                          "/scenes/" +
                            encodeURIComponent(selected.id) +
                            "/preview",
                        ),
                      )
                    }
                  >
                    {t("preview")}
                  </Action>
                )}
                {selected.download_url && (
                  <Action
                    run={async () => {
                      await api(
                        "/scenes/" +
                          encodeURIComponent(selected.id) +
                          "/download",
                        { method: "POST" },
                      );
                      await getJobs();
                    }}
                  >
                    {t("download")}
                  </Action>
                )}
              </div>
              {preview && (
                <img
                  className="preview-image"
                  src={preview}
                  alt={selected.name}
                />
              )}
              <details>
                <summary>{t("details")}</summary>
                <pre dir="ltr">{JSON.stringify(selected.details, null, 2)}</pre>
              </details>
            </div>
          )}
        </section>
      </div>
      {jobs.length > 0 && (
        <section className="panel">
          <header className="panel-header">
            <h2>{t("downloadJobs")}</h2>
          </header>
          {jobs.map((j) => (
            <div className="download-row" key={j.id}>
              <span className="break mono">{j.scene_id}</span>
              <span>
                {j.status} · {number(j.bytes_received / 1e6, "MB")}
              </span>
              {j.error && <span>{j.error}</span>}
              {j.status === "complete" && (
                <Action
                  secondary
                  run={() =>
                    saveFile("/downloads/" + j.id + "/file", j.id + ".zip")
                  }
                >
                  {t("download")}
                </Action>
              )}
            </div>
          ))}
        </section>
      )}
      <Comparison />
    </>
  );
}
