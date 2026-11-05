import { useState } from "react";
import { api } from "./api";
import { useT } from "./i18n";
import { Action, Notice } from "./ui";
export default function Hub({ reload }: { reload: () => Promise<void> }) {
  const t = useT(),
    [id, setId] = useState(""),
    [name, setName] = useState(""),
    [type, setType] = useState("rest"),
    [coverage, setCoverage] = useState(""),
    [payload, setPayload] = useState("[]"),
    [result, setResult] = useState("");
  return (
    <>
      <Notice>{t("hubNote")}</Notice>
      <div className="two-columns">
        <section className="panel padded">
          <h2>{t("registerSource")}</h2>
          <div className="form-grid">
            <label>
              {t("sourceId")}
              <input
                dir="ltr"
                value={id}
                onChange={(e) => setId(e.target.value)}
              />
            </label>
            <label>
              {t("name")}
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label>
              {t("sourceType")}
              <select value={type} onChange={(e) => setType(e.target.value)}>
                {["rest", "websocket", "mqtt", "serial", "phone", "radar"].map(
                  (x) => (
                    <option key={x}>{x}</option>
                  ),
                )}
              </select>
            </label>
            <label>
              {t("coverage")}
              <input
                value={coverage}
                onChange={(e) => setCoverage(e.target.value)}
              />
            </label>
          </div>
          <Action
            run={async () => {
              await api("/sources", {
                method: "POST",
                body: JSON.stringify({ id, name, source_type: type, coverage }),
              });
              setResult(t("saved"));
              await reload();
            }}
          >
            {t("register")}
          </Action>
          <Notice>{t("sensorRange")}</Notice>
          <a
            className="text-link"
            href="/docs"
            target="_blank"
            rel="noreferrer"
          >
            {t("apiDocs")} ↗
          </a>
        </section>
        <section className="panel padded">
          <h2>{t("ingest")}</h2>
          <label>
            {t("payloadJSON")}
            <textarea
              rows={17}
              dir="ltr"
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
            />
          </label>
          <Action
            run={async () => {
              const r = await api("/ingest", {
                method: "POST",
                body: JSON.stringify(JSON.parse(payload)),
              });
              setResult(JSON.stringify(r, null, 2));
              await reload();
            }}
          >
            {t("send")}
          </Action>
          {result && <pre dir="ltr">{result}</pre>}
        </section>
      </div>
    </>
  );
}
