import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowUpRight,
  Camera,
  ChevronRight,
  CircleHelp,
  Compass,
  Database,
  Globe,
  History as HistoryIcon,
  Layers,
  Menu,
  Plane,
  Radio,
  Radar,
  RefreshCw,
  Satellite as SatelliteIcon,
  Settings as SettingsIcon,
  Ship,
  SlidersHorizontal,
  TrafficCone,
  X,
  type LucideIcon,
} from "lucide-react";
import { api, getToken } from "./api";
import { date, LanguageContext, number, useT } from "./i18n";
import type { Area, Observation, Scene, Source } from "./types";
const RadarMap = lazy(() => import("./RadarMap"));
const Cameras = lazy(() => import("./Cameras"));
const Satellite = lazy(() => import("./Satellite"));
const Hub = lazy(() => import("./Hub"));
const History = lazy(() => import("./History"));
const SourceDiagnostics = lazy(() => import("./SourceDiagnostics"));
import { Action, Empty, Evidence, Notice, ObservationTable } from "./ui";

const pages: [string, LucideIcon][] = [
  ["radar", Radar],
  ["cameras", Camera],
  ["traffic", TrafficCone],
  ["aircraft", Plane],
  ["marine", Ship],
  ["satellite", SatelliteIcon],
  ["hub", Layers],
  ["history", HistoryIcon],
  ["diagnostics", Activity],
  ["settings", SettingsIcon],
];
const blankRings: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};
function Login({
  onLogin,
  toggleLanguage,
}: {
  onLogin: () => void;
  toggleLanguage: () => void;
}) {
  const t = useT(),
    [token, setToken] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    sessionStorage.setItem("nile_token", token);
    try {
      await api("/settings");
      onLogin();
    } catch {
      sessionStorage.removeItem("nile_token");
      setError(t("loginError"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login">
      <button className="language-button" onClick={toggleLanguage}>
        <Globe size={16} />
        {t("languageSwitch")}
      </button>
      <div className="login-brand">
        <Radar size={30} />
        <span>{t("brand")}</span>
      </div>
      <div className="login-content">
        <span className="eyebrow">{t("subbrand")}</span>
        <h1>{t("loginTitle")}</h1>
        <p>{t("loginNote")}</p>
        <form onSubmit={submit}>
          <label>
            {t("token")}
            <input
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              required
              minLength={24}
              dir="ltr"
            />
          </label>
          <button disabled={busy} className="button" type="submit">
            {busy ? t("waiting") : t("connect")}
            <ArrowUpRight size={18} />
          </button>
          {error && (
            <p className="inline-error" role="alert">
              {error}
            </p>
          )}
        </form>
        <span className="mono small muted">{t("localOnly")}</span>
      </div>
    </div>
  );
}

function Settings({
  area,
  save,
  logout,
  toggleLanguage,
}: {
  area: Area;
  save: (a: Area) => Promise<void>;
  logout: () => void;
  toggleLanguage: () => void;
}) {
  const t = useT(),
    [draft, setDraft] = useState(area),
    [saved, setSaved] = useState(false);
  useEffect(() => {
    setDraft(area);
  }, [area]);
  return (
    <>
      <Notice>{t("settingsNote")}</Notice>
      <section className="panel padded settings-panel">
        <h2>{t("coordinates")}</h2>
        <div className="form-grid">
          <label>
            {t("latitude")}
            <input
              type="number"
              min="-90"
              max="90"
              step="any"
              value={draft.latitude}
              onChange={(e) =>
                setDraft({ ...draft, latitude: Number(e.target.value) })
              }
            />
          </label>
          <label>
            {t("longitude")}
            <input
              type="number"
              min="-180"
              max="180"
              step="any"
              value={draft.longitude}
              onChange={(e) =>
                setDraft({ ...draft, longitude: Number(e.target.value) })
              }
            />
          </label>
          <label>
            {t("radius")} · {number(draft.radius_m / 1000, "km")}
            <input
              type="range"
              min="1000"
              max="5000"
              step="1000"
              value={draft.radius_m}
              onChange={(e) =>
                setDraft({ ...draft, radius_m: Number(e.target.value) })
              }
            />
          </label>
        </div>
        <Action
          run={async () => {
            await save(draft);
            setSaved(true);
          }}
        >
          {t("save")}
        </Action>
        {saved && (
          <span className="saved" role="status">
            {t("saved")}
          </span>
        )}
        <hr />
        <h2>{t("language")}</h2>
        <button className="button secondary" onClick={toggleLanguage}>
          <Globe size={16} />
          {t("languageSwitch")}
        </button>
        <hr />
        <Notice>{t("securityNote")}</Notice>
        <button className="button secondary" onClick={logout}>
          {t("logout")}
        </button>
      </section>
      <section className="panel padded">
        <h2>{t("attribution")}</h2>
        <p>{t("mapAttribution")}</p>
        <p>{t("dataAttribution")}</p>
        <p>{t("sensorRange")}</p>
      </section>
    </>
  );
}
function Workspace({
  logout,
  toggleLanguage,
}: {
  logout: () => void;
  toggleLanguage: () => void;
}) {
  const t = useT();
  const [page, setPage] = useState(
      pages.some(([p]) => p === location.hash.slice(1))
        ? location.hash.slice(1)
        : "radar",
    ),
    [nav, setNav] = useState(false),
    [sources, setSources] = useState<Source[]>([]),
    [items, setItems] = useState<Observation[]>([]),
    [scenes, setScenes] = useState<Scene[]>([]),
    [area, setArea] = useState<Area | null>(null),
    [rings, setRings] = useState(blankRings),
    [sourceFilter, setSourceFilter] = useState(""),
    [selected, setSelected] = useState<Observation | null>(null),
    [connection, setConnection] = useState("connecting"),
    [error, setError] = useState(""),
    [, setTick] = useState(0);
  const currentPage = useRef(page);
  const reload = useCallback(async () => {
    try {
      const [a, s, o, sc, r] = await Promise.all([
        api<Area>("/settings"),
        api<Source[]>("/sources"),
        api<Observation[]>("/observations?live=true"),
        api<Scene[]>("/scenes"),
        api<GeoJSON.FeatureCollection>("/coverage"),
      ]);
      setArea((prev) =>
        prev &&
        prev.latitude === a.latitude &&
        prev.longitude === a.longitude &&
        prev.radius_m === a.radius_m
          ? prev
          : a,
      );
      setSources(s);
      setItems(o);
      setScenes(sc);
      setRings((prev) =>
        JSON.stringify(prev) === JSON.stringify(r) ? prev : r,
      );
      setConnection("connected");
      setError("");
    } catch (e) {
      setConnection("disconnected");
      setError(String(e));
      throw e;
    }
  }, []);
  useEffect(() => {
    void reload().catch(() => {});
    const id = setInterval(() => {
      void reload().catch(() => {});
    }, 15000);
    const tick = setInterval(() => setTick((x) => x + 1), 5000);
    return () => {
      clearInterval(id);
      clearInterval(tick);
    };
  }, [reload]);
  useEffect(() => {
    let stopped = false,
      ws: WebSocket | undefined,
      timer: ReturnType<typeof setTimeout>;
    function connect() {
      ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/stream`,
      );
      ws.onopen = () => ws?.send(JSON.stringify({ token: getToken() }));
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "snapshot") {
            setItems(data.observations);
            setSources(data.sources);
            setConnection("connected");
          }
        } catch {
          /* Invalid transport payload is ignored; periodic HTTP checks remain active. */
        }
      };
      ws.onclose = () => {
        if (!stopped) timer = setTimeout(connect, 10000);
      };
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, []);
  useEffect(() => {
    const onHash = () => {
      const p = location.hash.slice(1);
      if (pages.some(([s]) => s === p) && currentPage.current !== p) {
        currentPage.current = p;
        setPage(p);
        setNav(false);
      }
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  function navigate(p: string) {
    // Ignore the later hashchange for this already-applied route. Otherwise it can
    // close a mobile menu that the user reopened immediately after navigation.
    currentPage.current = p;
    setPage(p);
    location.hash = p;
    setNav(false);
    setSelected(null);
  }
  async function save(a: Area) {
    await api("/settings", { method: "PUT", body: JSON.stringify(a) });
    await reload();
  }
  async function select(o: Observation) {
    setSelected(o);
    try {
      setSelected(await api("/observations/" + o.observation_id));
    } catch {
      /* Current row still contains its source and measurement basis. */
    }
  }
  const live = items.filter((o) => {
    const age =
      (Date.now() - Date.parse(o.observed_at || o.received_at)) / 1000;
    return (
      age >= -120 &&
      age <=
        ({ adsb: 60, ais: 180, camera: 30, phone: 30, radar: 30, traffic: 300 }[
          o.source_type
        ] || 300)
    );
  });
  const filtered = live.filter(
    (o) => !sourceFilter || o.source_id === sourceFilter,
  );
  const positioned = filtered.filter(
      (o) => o.latitude !== null && o.longitude !== null,
    ),
    unlocated = filtered.filter((o) => o.latitude === null);
  const healthy = sources.filter(
    (s) =>
      s.enabled &&
      ["available", "empty", "historical_available", "connected"].includes(
        s.availability,
      ),
  ).length;
  return (
    <div className="app-shell">
      <aside className={"sidebar " + (nav ? "open" : "")}>
        <a href="#radar" className="brand" onClick={() => navigate("radar")}>
          <Radar size={28} strokeWidth={1.5} />
          <span>
            {t("brand")}
            <small>{t("subbrand")}</small>
          </span>
        </a>
        <span className="nav-heading">{t("workspace")}</span>
        <nav>
          {pages.map(([key, Icon]) => (
            <button
              key={key}
              onClick={() => navigate(key)}
              className={page === key ? "current" : ""}
              aria-current={page === key ? "page" : undefined}
            >
              <Icon size={18} strokeWidth={1.6} />
              <span>{t(key)}</span>
              {page === key && <ChevronRight size={14} className="nav-arrow" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="side-coordinate">
            <Compass size={18} />
            <span className="mono">
              {area?.latitude.toFixed(5) || "—"}
              <br />
              {area?.longitude.toFixed(5) || "—"}
            </span>
            <span>WGS84</span>
          </div>
          <button className="language-button" onClick={toggleLanguage}>
            <Globe size={16} />
            {t("languageSwitch")}
          </button>
          <a href="/docs" target="_blank" rel="noreferrer">
            <CircleHelp size={15} />
            {t("apiDocs")} ↗
          </a>
        </div>
      </aside>
      {nav && (
        <button
          className="nav-shade"
          onClick={() => setNav(false)}
          aria-label={t("close")}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="icon-button menu-button"
              aria-label={t("workspace")}
              onClick={() => setNav(!nav)}
            >
              {nav ? <X size={20} /> : <Menu size={20} />}
            </button>
            <span className="muted">{t("workspace")}</span>
            <ChevronRight size={14} />
            <strong>{t(page)}</strong>
          </div>
          <div className="connection">
            <span className={"connection-dot " + connection} />
            <span>{t(connection)}</span>
          </div>
        </header>
        <main>
          <div className="page-intro">
            <div>
              <div className="eyebrow">
                <span className="tiny-square" />
                {page === "radar" ? t("localOnly") : t("workspace")}
              </div>
              <h1>{page === "radar" ? t("radarTitle") : t(page)}</h1>
              {page === "radar" && <p>{t("radarSubtitle")}</p>}
            </div>
            <span className="coordinate-stamp mono" dir="ltr">
              {area
                ? `${area.latitude.toFixed(5)} / ${area.longitude.toFixed(5)}`
                : "—"}
              <small>
                {t("searchArea")} · {area ? area.radius_m / 1000 : "—"} km
              </small>
            </span>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              {t("disconnected")} · {error}
              <br />
              {t("offlineNote")}
            </div>
          )}
          {!area ? (
            <div className="panel padded">
              {t("loading")}
              <Action secondary run={reload}>
                {t("refresh")}
              </Action>
            </div>
          ) : (
            <>
              {page === "radar" && (
                <>
                  <div className="metrics">
                    {[
                      [t("active"), positioned.length, Radio],
                      [
                        t("reporting"),
                        `${healthy} / ${sources.length}`,
                        Activity,
                      ],
                      [t("historicalScenes"), scenes.length, SatelliteIcon],
                      [t("searchArea"), `${area.radius_m / 1000} km`, Compass],
                    ].map(([label, value, Icon]) => {
                      const I = Icon as LucideIcon;
                      return (
                        <div className="metric" key={String(label)}>
                          <div>
                            <span>{String(label)}</span>
                            <I size={17} strokeWidth={1.5} />
                          </div>
                          <strong dir="ltr">{String(value)}</strong>
                          <span className="metric-detail">
                            {label === t("active")
                              ? t("live")
                              : label === t("historicalScenes")
                                ? t("historical")
                                : "WGS84"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="radar-toolbar">
                    <label>
                      <SlidersHorizontal size={15} />
                      {t("source")}
                      <select
                        value={sourceFilter}
                        onChange={(e) => setSourceFilter(e.target.value)}
                      >
                        <option value="">{t("allSources")}</option>
                        {sources.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="range-control">
                      {t("radius")}
                      <input
                        type="range"
                        min="1000"
                        max="5000"
                        step="1000"
                        aria-label={t("radius")}
                        value={area.radius_m}
                        onChange={(e) => {
                          const a = {
                            ...area,
                            radius_m: Number(e.target.value),
                          };
                          setArea(a);
                          void save(a).catch((e) => setError(String(e)));
                        }}
                      />
                      <strong dir="ltr">{area.radius_m / 1000} km</strong>
                    </label>
                    <Action
                      secondary
                      run={async () => {
                        await Promise.all(
                          sources
                            .filter(
                              (s) =>
                                s.enabled &&
                                [
                                  "adsb_lol",
                                  "asf",
                                  "copernicus",
                                  "sensor_community",
                                  "openaq",
                                  "tomtom",
                                ].includes(s.id),
                            )
                            .map((s) =>
                              api("/sources/" + s.id + "/refresh", {
                                method: "POST",
                              }),
                            ),
                        );
                        await reload();
                      }}
                    >
                      <RefreshCw size={14} />
                      {t("refreshAll")}
                    </Action>
                  </div>
                  <div className="radar-layout">
                    <section className="panel map-panel">
                      <header className="panel-header">
                        <h2>{t("mapTitle")}</h2>
                        <span className="badge" dir="ltr">
                          {area.radius_m / 1000} km · WGS84
                        </span>
                      </header>
                      <RadarMap
                        area={area}
                        observations={
                          connection === "connected" ? positioned : []
                        }
                        rings={rings}
                        onSelect={(o) => void select(o)}
                      />
                      <footer className="map-footer">
                        <Compass size={14} />
                        {t("mapNote")}
                      </footer>
                    </section>
                    <section className="panel observation-feed">
                      <header className="panel-header">
                        <h2>{t("latest")}</h2>
                        <span className="mono">
                          {filtered.length.toString().padStart(2, "0")}
                        </span>
                      </header>
                      {filtered.length ? (
                        <div className="feed-items">
                          {filtered.slice(0, 20).map((o) => (
                            <button
                              className="feed-item"
                              key={o.observation_id}
                              onClick={() => void select(o)}
                            >
                              <div className="feed-icon">
                                {o.source_type === "adsb" ? (
                                  <Plane size={18} />
                                ) : o.source_type === "ais" ? (
                                  <Ship size={18} />
                                ) : (
                                  <Radio size={18} />
                                )}
                              </div>
                              <div>
                                <strong>
                                  {t(o.object_type)}
                                  <ArrowUpRight size={14} />
                                </strong>
                                <span>
                                  {o.source_id} · {o.track_id || "—"}
                                </span>
                                <small>
                                  {o.distance_m === null
                                    ? t("unlocated")
                                    : number(o.distance_m, "m")}{" "}
                                  ·{" "}
                                  {o.observed_at
                                    ? number(
                                        Math.max(
                                          0,
                                          (Date.now() -
                                            Date.parse(o.observed_at)) /
                                            1000,
                                        ),
                                        "s",
                                      )
                                    : t("unknown")}
                                </small>
                              </div>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <Empty />
                      )}
                      <div className="feed-footer">
                        <Database size={15} />
                        {t("limitNote")}
                      </div>
                    </section>
                  </div>
                  {unlocated.length > 0 && (
                    <Notice>
                      {unlocated.length} · {t("unlocatedNote")}
                    </Notice>
                  )}
                  <section className="panel">
                    <header className="panel-header">
                      <h2>{t("sourceHealth")}</h2>
                      <button
                        className="text-link"
                        onClick={() => navigate("diagnostics")}
                      >
                        {t("diagnostics")} ↗
                      </button>
                    </header>
                    <div className="source-strip">
                      {sources.slice(0, 6).map((s) => (
                        <button
                          key={s.id}
                          onClick={() => navigate("diagnostics")}
                        >
                          <span>{s.name}</span>
                          <strong>
                            {t(
                              s.availability === "connected"
                                ? "sourceConnected"
                                : s.availability,
                            )}
                          </strong>
                          <small>
                            {s.last_success_at ? date(s.last_success_at) : "—"}
                          </small>
                        </button>
                      ))}
                    </div>
                  </section>
                </>
              )}
              {page === "cameras" && <Cameras />}
              {["aircraft", "marine"].includes(page) && (
                <>
                  <Notice>
                    {t(page === "aircraft" ? "aircraftNote" : "marineNote")}
                  </Notice>
                  <section className="panel">
                    <ObservationTable
                      items={live.filter(
                        (o) =>
                          o.source_type ===
                          (page === "aircraft" ? "adsb" : "ais"),
                      )}
                      onSelect={(o) => void select(o)}
                    />
                  </section>
                  <Notice>
                    {page === "aircraft" &&
                    live.filter((o) => o.source_type === "adsb").length === 0
                      ? t("emptySky")
                      : t("noCoverage")}
                  </Notice>
                </>
              )}
              {page === "traffic" && (
                <>
                  <Notice>{t("trafficNote")}</Notice>
                  <div className="traffic-grid">
                    {live
                      .filter((o) => o.source_type === "traffic")
                      .map((o) => (
                        <section
                          className="panel padded"
                          key={o.observation_id}
                        >
                          <span className="eyebrow">
                            TomTom · {t("road_segment")}
                          </span>
                          <h2>
                            {number(
                              o.speed_mps === null ? null : o.speed_mps * 3.6,
                              "km/h",
                            )}
                          </h2>
                          <dl className="detail-grid">
                            {[
                              [
                                "freeFlow",
                                number(
                                  o.details.free_flow_speed_kmh as
                                    number | null,
                                  "km/h",
                                ),
                              ],
                              [
                                "travelTime",
                                number(
                                  o.details.current_travel_time_s as
                                    number | null,
                                  "s",
                                ),
                              ],
                              [
                                "congestion",
                                number(
                                  typeof o.details.congestion_ratio === "number"
                                    ? o.details.congestion_ratio * 100
                                    : null,
                                  "%",
                                ),
                              ],
                              ["observed", date(o.observed_at)],
                              ["retrievalTime", date(o.received_at)],
                            ].map(([key, value]) => (
                              <div key={key}>
                                <dt>{t(key)}</dt>
                                <dd>{value}</dd>
                              </div>
                            ))}
                          </dl>
                          <button
                            className="text-link"
                            onClick={() => void select(o)}
                          >
                            {t("evidence")} ↗
                          </button>
                        </section>
                      ))}
                  </div>
                  {!live.some((o) => o.source_type === "traffic") && <Empty />}
                  <section className="panel map-panel">
                    <RadarMap
                      area={area}
                      observations={live.filter(
                        (o) => o.source_type === "traffic",
                      )}
                      rings={rings}
                      onSelect={(o) => void select(o)}
                    />
                  </section>
                  <Notice>{t("notCertified")}</Notice>
                </>
              )}
              {page === "satellite" && (
                <Satellite
                  scenes={scenes}
                  area={area}
                  rings={rings}
                  reload={reload}
                />
              )}
              {page === "hub" && <Hub reload={reload} />}
              {page === "history" && (
                <History sources={sources} onSelect={(o) => void select(o)} />
              )}
              {page === "diagnostics" && (
                <SourceDiagnostics sources={sources} reload={reload} />
              )}
              {page === "settings" && (
                <Settings
                  area={area}
                  save={save}
                  logout={logout}
                  toggleLanguage={toggleLanguage}
                />
              )}
            </>
          )}
          <footer className="main-footer">
            <span>{t("brand")}</span>
            <span>{t("localOnly")}</span>
            <ArrowDownToLine size={14} />
          </footer>
        </main>
      </div>
      <Evidence item={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
export default function App() {
  const [language, setLanguage] = useState<"en" | "ar">(
      localStorage.getItem("nile_language") === "ar" ? "ar" : "en",
    ),
    [signedIn, setSignedIn] = useState(Boolean(getToken()));
  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
    localStorage.setItem("nile_language", language);
  }, [language]);
  function toggleLanguage() {
    setLanguage((x) => (x === "en" ? "ar" : "en"));
  }
  return (
    <LanguageContext.Provider value={language}>
      <Suspense
        fallback={
          <div className="padded">
            {language === "ar" ? "جارٍ التحميل…" : "Loading…"}
          </div>
        }
      >
        {signedIn ? (
          <Workspace
            logout={() => {
              sessionStorage.removeItem("nile_token");
              setSignedIn(false);
            }}
            toggleLanguage={toggleLanguage}
          />
        ) : (
          <Login
            onLogin={() => setSignedIn(true)}
            toggleLanguage={toggleLanguage}
          />
        )}
      </Suspense>
    </LanguageContext.Provider>
  );
}
