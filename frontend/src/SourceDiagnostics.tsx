import { RefreshCw } from "lucide-react";
import { api } from "./api";
import { date, number, useT } from "./i18n";
import type { Source } from "./types";
import { Action, Notice } from "./ui";
const polling = [
  "adsb_lol",
  "asf",
  "copernicus",
  "tomtom",
  "sensor_community",
  "openaq",
];
export default function SourceDiagnostics({
  sources,
  reload,
}: {
  sources: Source[];
  reload: () => Promise<void>;
}) {
  const t = useT();
  return (
    <>
      <Notice>{t("noCoverage")}</Notice>
      <div className="source-grid">
        {sources.map((s) => (
          <article className="panel source-card" key={s.id}>
            <div className="card-top">
              <span className="eyebrow">{s.source_type}</span>
              <span className="badge">
                {t(
                  s.availability === "connected"
                    ? "sourceConnected"
                    : s.availability,
                )}
              </span>
            </div>
            <h3>{s.name}</h3>
            <p className="muted">{s.coverage}</p>
            <dl className="detail-grid">
              <div>
                <dt>{t("authentication")}</dt>
                <dd>{t("auth_" + s.auth_state)}</dd>
              </div>
              <div>
                <dt>{t("latency")}</dt>
                <dd>{number(s.latency_ms, "ms", 0)}</dd>
              </div>
              <div>
                <dt>{t("interval")}</dt>
                <dd>{number(s.update_interval, "s", 0)}</dd>
              </div>
              <div>
                <dt>{t("count")}</dt>
                <dd>{number(s.last_count, "", 0)}</dd>
              </div>
              <div className="wide">
                <dt>{t("lastSuccess")}</dt>
                <dd>{date(s.last_success_at)}</dd>
              </div>
              <div className="wide">
                <dt>{t("lastObservation")}</dt>
                <dd>{date(s.last_observation_at)}</dd>
              </div>
            </dl>
            <div className="source-note">
              <strong>{t("quality")}</strong>
              <p>{s.quality}</p>
              {s.error && (
                <>
                  <strong>{t("errors")}</strong>
                  <p>{s.error}</p>
                </>
              )}
            </div>
            <div className="actions">
              {polling.includes(s.id) && (
                <Action
                  secondary
                  run={async () => {
                    await api(`/sources/${s.id}/refresh`, { method: "POST" });
                    await reload();
                  }}
                >
                  <RefreshCw size={14} />
                  {t("refresh")}
                </Action>
              )}
              <Action
                secondary
                run={async () => {
                  await api(`/sources/${s.id}`, {
                    method: "PATCH",
                    body: JSON.stringify({ enabled: !s.enabled }),
                  });
                  await reload();
                }}
              >
                {t(s.enabled ? "disable" : "enable")}
              </Action>
              {s.documentation_url && (
                <a
                  className="text-link"
                  href={s.documentation_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {t("apiDocs")} ↗
                </a>
              )}
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
