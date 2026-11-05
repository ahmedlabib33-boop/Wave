import { useState, type ReactNode } from "react";
import { ArrowUpRight, LoaderCircle, Radio, X } from "lucide-react";
import type { Observation } from "./types";
import { date, number, useT } from "./i18n";

export function Action({
  run,
  children,
  secondary = false,
}: {
  run: () => Promise<unknown>;
  children: ReactNode;
  secondary?: boolean;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const t = useT();
  return (
    <span className="action-wrap">
      <button
        type="button"
        className={secondary ? "button secondary" : "button"}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await run();
          } catch (e) {
            setError(e instanceof Error ? e.message : t("error"));
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? <LoaderCircle size={15} className="spin" /> : null}
        {busy ? t("waiting") : children}
      </button>
      {error && (
        <span className="inline-error" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
export function Empty({ message }: { message?: string }) {
  const t = useT();
  return (
    <div className="empty">
      <Radio size={28} strokeWidth={1} />
      <h3>{message || t("noObservations")}</h3>
      <p>{t("emptyExplanation")}</p>
    </div>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return <p className="notice">{children}</p>;
}
export function ObservationTable({
  items,
  onSelect,
}: {
  items: Observation[];
  onSelect: (o: Observation) => void;
}) {
  const t = useT();
  if (!items.length) return <Empty />;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {[
              "object",
              "source",
              "distance",
              "bearing",
              "speed",
              "altitude",
              "observed",
              "method",
            ].map((x) => (
              <th key={x}>{t(x)}</th>
            ))}
            <th>
              <span className="sr-only">{t("details")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((o) => (
            <tr key={o.observation_id}>
              <td>
                <strong>{t(o.object_type)}</strong>
                <small>{o.track_id || "—"}</small>
              </td>
              <td>{o.source_id}</td>
              <td className="numeric">{number(o.distance_m, "m")}</td>
              <td className="numeric">{number(o.bearing_deg, "°")}</td>
              <td className="numeric">
                {number(
                  o.speed_mps === null ? null : o.speed_mps * 3.6,
                  "km/h",
                )}
              </td>
              <td className="numeric">{number(o.altitude, "m")}</td>
              <td>{o.observed_at ? date(o.observed_at) : t("dateMissing")}</td>
              <td>{t(o.measurement_method)}</td>
              <td>
                <button
                  className="icon-button"
                  onClick={() => onSelect(o)}
                  aria-label={t("showEvidence")}
                >
                  <ArrowUpRight size={18} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Evidence({
  item,
  onClose,
}: {
  item: Observation | null;
  onClose: () => void;
}) {
  const t = useT();
  if (!item) return null;
  const fields = [
    ["object", t(item.object_type)],
    ["source", item.source_id],
    ["method", t(item.measurement_method)],
    [
      "position",
      item.latitude === null ? "—" : `${item.latitude}, ${item.longitude}`,
    ],
    ["distance", number(item.distance_m, "m")],
    ["bearing", number(item.bearing_deg, "°")],
    [
      "speed",
      number(item.speed_mps === null ? null : item.speed_mps * 3.6, "km/h"),
    ],
    ["accuracy", number(item.location_accuracy_m, "m")],
    ["confidence", number(item.confidence)],
    ["observed", date(item.observed_at)],
    ["received", date(item.received_at)],
    [
      "freshness",
      item.observed_at
        ? number(
            Math.max(0, (Date.now() - Date.parse(item.observed_at)) / 1000),
            "s",
          )
        : t("unknown"),
    ],
  ];
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="evidence"
        role="dialog"
        aria-modal="true"
        aria-label={t("evidence")}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <div>
            <span className="eyebrow">{t("evidence")}</span>
            <h2>{t(item.object_type)}</h2>
          </div>
          <button
            autoFocus
            className="icon-button"
            onClick={onClose}
            aria-label={t("close")}
          >
            <X />
          </button>
        </header>
        <dl className="detail-grid">
          {fields.map(([k, v]) => (
            <div key={k}>
              <dt>{t(k)}</dt>
              <dd>
                <bdi>{v}</bdi>
              </dd>
            </div>
          ))}
        </dl>
        <p className="mono small break">{item.observation_id}</p>
        <pre dir="ltr">
          {JSON.stringify(
            {
              details: item.details,
              raw_data_reference: item.raw_data_reference,
              raw: item.raw,
            },
            null,
            2,
          )}
        </pre>
        <button className="button secondary" onClick={onClose}>
          {t("close")}
        </button>
      </section>
    </div>
  );
}
