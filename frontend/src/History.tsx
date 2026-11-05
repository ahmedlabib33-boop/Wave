import { useEffect, useState } from "react";
import { api } from "./api";
import { useT } from "./i18n";
import type { Observation, Source } from "./types";
import { Action, Notice, ObservationTable } from "./ui";
export default function History({
  sources,
  onSelect,
}: {
  sources: Source[];
  onSelect: (o: Observation) => void;
}) {
  const t = useT(),
    [source, setSource] = useState(""),
    [object, setObject] = useState(""),
    [since, setSince] = useState(""),
    [until, setUntil] = useState(""),
    [items, setItems] = useState<Observation[]>([]),
    [page, setPage] = useState(0),
    [error, setError] = useState("");
  async function search(target = 0) {
    const params = new URLSearchParams({
      limit: "100",
      offset: String(target * 100),
    });
    if (source) params.set("source_id", source);
    if (object) params.set("object_type", object);
    if (since) params.set("since", since + "Z");
    if (until) params.set("until", until + "Z");
    setItems(await api("/observations?" + params));
    setPage(target);
  }
  useEffect(() => {
    void search().catch((e) => setError(String(e)));
  }, []);
  return (
    <>
      <Notice>{t("historyNote")}</Notice>
      <section className="panel search-bar">
        <label>
          {t("source")}
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">{t("allSources")}</option>
            {sources.map((s) => (
              <option value={s.id} key={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("object")}
          <input value={object} onChange={(e) => setObject(e.target.value)} />
        </label>
        <label>
          {t("start")}
          <input
            type="datetime-local"
            value={since}
            onChange={(e) => setSince(e.target.value)}
          />
        </label>
        <label>
          {t("end")}
          <input
            type="datetime-local"
            value={until}
            onChange={(e) => setUntil(e.target.value)}
          />
        </label>
        <Action run={() => search()}>{t("search")}</Action>
      </section>
      {error && <p role="alert">{error}</p>}
      <section className="panel">
        <ObservationTable items={items} onSelect={onSelect} />
      </section>
      <div className="pagination">
        <Action secondary run={() => search(Math.max(0, page - 1))}>
          {t("previous")}
        </Action>
        <span>
          {t("page")} {page + 1}
        </span>
        <Action secondary run={() => search(page + 1)}>
          {t("next")}
        </Action>
      </div>
    </>
  );
}
