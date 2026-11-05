import { useEffect, useState } from "react";
import { api } from "./api";
import { date, useT } from "./i18n";
import { Action, Notice } from "./ui";

interface Region {
  south: number;
  west: number;
  north: number;
  east: number;
}
interface Candidate {
  id: string;
  name: string;
  provider: string;
  source_ref: string | null;
  latitude: number | null;
  longitude: number | null;
  permission_state: string;
  permission_evidence: string | null;
  url_env: string | null;
  protocol: string | null;
  checked_at: string | null;
  verification_status: string;
  error: string | null;
  camera_id: string | null;
  frame_width: number | null;
  frame_height: number | null;
}
interface Run {
  id: string;
  kind: string;
  status: string;
  started_at: string;
  returned_count: number | null;
  error: string | null;
}

function CandidateCard({
  candidate,
  reload,
  onIntegrated,
}: {
  candidate: Candidate;
  reload: () => Promise<void>;
  onIntegrated: () => Promise<void>;
}) {
  const t = useT(),
    [permission, setPermission] = useState(candidate.permission_state),
    [evidence, setEvidence] = useState(candidate.permission_evidence || ""),
    [urlEnv, setUrlEnv] = useState(candidate.url_env || ""),
    [protocol, setProtocol] = useState(candidate.protocol || "rtsp"),
    [authorized, setAuthorized] = useState(false);
  const permitted = ["public_documented", "owner_authorized"].includes(
    candidate.permission_state,
  );
  return (
    <article className="panel padded candidate-card">
      <div className="card-top">
        <h3>{candidate.name}</h3>
        <span className="badge">{t(candidate.verification_status)}</span>
      </div>
      <p className="small muted">{candidate.provider}</p>
      <p className="mono small" dir="ltr">
        {candidate.latitude === null
          ? "—"
          : `${candidate.latitude}, ${candidate.longitude}`}
      </p>
      <p className="small muted">
        {t("permission_" + candidate.permission_state)} ·{" "}
        {t("cameraMetadataOnly")}
      </p>
      {candidate.source_ref && (
        <a
          className="text-link"
          href={candidate.source_ref}
          target="_blank"
          rel="noreferrer"
        >
          {t("sourceDocumentation")} ↗
        </a>
      )}
      <details className="permission-editor">
        <summary>{t("permissionAndStream")}</summary>
        <Notice>{t("permissionEvidenceNote")}</Notice>
        <div className="form-grid">
          <label>
            {t("permissionState")}
            <select
              value={permission}
              onChange={(e) => setPermission(e.target.value)}
            >
              {[
                "unknown",
                "public_documented",
                "owner_authorized",
                "denied",
              ].map((s) => (
                <option key={s} value={s}>
                  {t("permission_" + s)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("urlEnv")}
            <input
              dir="ltr"
              value={urlEnv}
              placeholder="CAMERA_MAIN_URL"
              onChange={(e) => setUrlEnv(e.target.value)}
            />
          </label>
          <label>
            {t("protocol")}
            <select
              value={protocol}
              onChange={(e) => setProtocol(e.target.value)}
            >
              {["rtsp", "http", "hls", "onvif"].map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
        </div>
        <label>
          {t("permissionEvidence")}
          <textarea
            rows={3}
            value={evidence}
            onChange={(e) => setEvidence(e.target.value)}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={authorized}
            onChange={(e) => setAuthorized(e.target.checked)}
          />
          {t("detectionPermission")}
        </label>
        <Action
          secondary
          run={async () => {
            await api(`/discovery/candidates/${candidate.id}/permission`, {
              method: "PUT",
              body: JSON.stringify({
                permission_state: permission,
                evidence: evidence || null,
                url_env: urlEnv || null,
                protocol: urlEnv ? protocol : null,
                authorized,
              }),
            });
            await reload();
          }}
        >
          {t("savePermission")}
        </Action>
      </details>
      <div className="actions">
        {permitted && candidate.url_env && (
          <Action
            secondary
            run={async () => {
              await api(`/discovery/candidates/${candidate.id}/verify`, {
                method: "POST",
              });
              await reload();
            }}
          >
            {t("verifyStream")}
          </Action>
        )}
        {candidate.verification_status === "frame_verified" && (
          <Action
            run={async () => {
              await api(`/discovery/candidates/${candidate.id}/integrate`, {
                method: "POST",
                body: JSON.stringify({ authorized: true }),
              });
              await reload();
              await onIntegrated();
            }}
          >
            {t(candidate.camera_id ? "linkedCamera" : "integrateCamera")}
          </Action>
        )}
      </div>
      {candidate.checked_at && (
        <p className="small muted">
          {t("lastStreamCheck")} · <bdi>{date(candidate.checked_at)}</bdi> ·{" "}
          <bdi>
            {candidate.frame_width} × {candidate.frame_height}
          </bdi>
        </p>
      )}
      {candidate.error && (
        <p role="status" className="inline-error">
          {candidate.error}
        </p>
      )}
      {candidate.camera_id && (
        <p className="mono small">{candidate.camera_id}</p>
      )}
    </article>
  );
}

export default function CameraDiscovery({
  onIntegrated,
}: {
  onIntegrated: () => Promise<void>;
}) {
  const t = useT(),
    [region, setRegion] = useState<Region | null>(null),
    [candidates, setCandidates] = useState<Candidate[]>([]),
    [runs, setRuns] = useState<Run[]>([]),
    [error, setError] = useState(""),
    [result, setResult] = useState<{
      returned_count: number;
      truncated?: boolean;
    } | null>(null);
  const [name, setName] = useState(""),
    [reference, setReference] = useState(""),
    [lat, setLat] = useState(""),
    [lon, setLon] = useState("");
  async function reload() {
    const [area, records, history] = await Promise.all([
      api<Region>("/discovery/area"),
      api<Candidate[]>("/discovery/candidates"),
      api<Run[]>("/discovery/runs"),
    ]);
    setRegion({
      south: area.south,
      west: area.west,
      north: area.north,
      east: area.east,
    });
    setCandidates(records);
    setRuns(history);
    setError("");
  }
  useEffect(() => {
    void reload().catch((e) => setError(String(e)));
  }, []);
  return (
    <details className="panel registration regional-discovery">
      <summary>{t("regionalDiscovery")}</summary>
      <Notice>{t("regionalDiscoveryNote")}</Notice>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      {region && (
        <>
          <div className="form-grid discovery-bbox">
            {(["south", "west", "north", "east"] as const).map((key) => (
              <label key={key}>
                {t("bbox_" + key)}
                <input
                  type="number"
                  step="any"
                  value={region[key]}
                  onChange={(e) =>
                    setRegion({ ...region, [key]: Number(e.target.value) })
                  }
                />
              </label>
            ))}
          </div>
          <div className="actions">
            <Action
              secondary
              run={async () => {
                await api("/discovery/area", {
                  method: "PUT",
                  body: JSON.stringify(region),
                });
                await reload();
              }}
            >
              {t("saveInvestigationArea")}
            </Action>
            <Action
              run={async () => {
                try {
                  setResult(await api("/discovery/search", { method: "POST" }));
                } finally {
                  await reload();
                }
              }}
            >
              {t("searchCameraMetadata")}
            </Action>
          </div>
        </>
      )}
      {result && (
        <p className="notice">
          {t("metadataReturned")} <bdi>{result.returned_count}</bdi> ·{" "}
          {t(result.truncated ? "searchIncomplete" : "inventoryNotCoverage")}
        </p>
      )}
      <details className="manual-candidate">
        <summary>{t("addCandidate")}</summary>
        <div className="form-grid">
          <label>
            {t("name")}
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            {t("sourceDocumentation")}
            <input
              type="url"
              dir="ltr"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
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
        </div>
        <Action
          secondary
          run={async () => {
            await api("/discovery/candidates", {
              method: "POST",
              body: JSON.stringify({
                name,
                source_ref: reference || null,
                latitude: lat === "" ? null : Number(lat),
                longitude: lon === "" ? null : Number(lon),
              }),
            });
            await reload();
            setName("");
            setReference("");
            setLat("");
            setLon("");
          }}
        >
          {t("registerCandidate")}
        </Action>
      </details>
      <div className="camera-grid candidate-grid">
        {candidates.map((candidate) => (
          <CandidateCard
            key={candidate.id}
            candidate={candidate}
            reload={reload}
            onIntegrated={onIntegrated}
          />
        ))}
      </div>
      {!candidates.length && <Notice>{t("noCameraCandidates")}</Notice>}
      <details>
        <summary>{t("discoveryHistory")}</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {[
                  "observed",
                  "sourceType",
                  "availability",
                  "count",
                  "errors",
                ].map((x) => (
                  <th key={x}>{t(x)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>
                    <bdi>{date(run.started_at)}</bdi>
                  </td>
                  <td>{t("run_" + run.kind)}</td>
                  <td>{t(run.status)}</td>
                  <td>{run.returned_count ?? "—"}</td>
                  <td>{run.error || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </details>
  );
}
