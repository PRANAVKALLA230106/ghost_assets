import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useGhostStore } from "../store";
import { formatINR } from "../format";
import { ASSET_TYPE_LABEL, LEVEL_COLOR, STATUS_LABEL, claimPathLabel, confidenceLabel } from "../labels";
import ClaimPackButton from "../components/ClaimPackButton";
import { useCaseContext } from "./CaseLayout";

/** Screen 4: one row per asset with how and where to claim it. */
export default function ClaimsPage() {
  const { caseId, deceasedName, openAsset } = useCaseContext();
  const assets = useGhostStore((s) => s.assets);
  const claims = useGhostStore((s) => s.claims);
  const done = useGhostStore((s) => s.done);

  const rows = useMemo(
    () => Object.values(assets).sort((a, b) => (b.est_value ?? 0) - (a.est_value ?? 0)),
    [assets],
  );
  const total = rows.reduce((sum, a) => sum + (a.est_value ?? 0), 0);
  const ready = rows.filter((a) => claims[a.id]).length;

  return (
    <div className="min-h-screen bg-page px-10 py-8 text-ink">
      <div className="flex gap-5 text-muted">
        <Link to={`/case/${caseId}`} className="hover:text-accent">← Live map</Link>
        <Link to={`/case/${caseId}/proof`} className="hover:text-accent">Proof: how sure are we? →</Link>
      </div>
      <div className="mt-2 flex items-end justify-between gap-6">
        <div>
          <h1 className="text-4xl font-semibold">Claims{deceasedName && <span className="text-muted"> · {deceasedName}</span>}</h1>
          <p className="mt-1 text-lg text-muted">
            {rows.length} assets worth <span className="text-accent">{formatINR(total)}</span> · claim path decided for {ready} of {rows.length}
            {!done && " · still running"}
          </p>
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="mt-10 text-muted">No assets yet. They appear here as the agent finds them.</p>
      ) : (
        <div className="mt-6 overflow-hidden rounded-lg bg-card">
          <table className="w-full text-left">
            <thead className="border-b border-page text-sm uppercase tracking-wide text-muted">
              <tr>
                <th className="px-5 py-3 font-medium">Asset</th>
                <th className="px-5 py-3 text-right font-medium">Value</th>
                <th className="px-5 py-3 font-medium">Claim path</th>
                <th className="px-5 py-3 font-medium">Where to submit</th>
                <th className="px-5 py-3 font-medium">Missing documents</th>
                <th className="px-5 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => {
                const claim = claims[a.id];
                const missing = claim?.documents.filter((d) => !d.have) ?? [];
                return (
                  <tr key={a.id} className="border-b border-page/60 align-top last:border-0">
                    <td className="px-5 py-4">
                      <button onClick={() => openAsset(a.id)} className="text-left hover:text-accent">
                        <div className="text-lg font-semibold">{a.institution}</div>
                        <div className="text-sm text-muted">
                          {ASSET_TYPE_LABEL[a.asset_type]}
                          {a.identifier && <> · <span className="font-mono">{a.identifier}</span></>}
                        </div>
                        <div className="text-xs text-muted">
                          {STATUS_LABEL[a.status]} ·{" "}
                          <span style={{ color: LEVEL_COLOR[confidenceLabel(a.confidence)] }}>
                            {confidenceLabel(a.confidence)} confidence ({Math.round(a.confidence * 100)}%)
                          </span>
                        </div>
                      </button>
                    </td>
                    <td className="px-5 py-4 text-right text-lg font-semibold tabular-nums text-accent">
                      {a.est_value != null ? formatINR(a.est_value) : "—"}
                    </td>
                    <td className="px-5 py-4">
                      {claim ? (
                        <span className="inline-block rounded-full border border-accent/60 px-3 py-1 text-sm text-accent">
                          {claimPathLabel(claim.path)}
                        </span>
                      ) : (
                        <span className="text-muted">Pending</span>
                      )}
                      {claim?.deadline_note && <div className="mt-1 text-xs text-muted">{claim.deadline_note}</div>}
                    </td>
                    <td className="px-5 py-4">{claim?.where ?? <span className="text-muted">—</span>}</td>
                    <td className="px-5 py-4">
                      {!claim ? (
                        <span className="text-muted">—</span>
                      ) : missing.length === 0 ? (
                        <span className="text-green-300">None, all in hand</span>
                      ) : (
                        <ul className="list-disc space-y-0.5 pl-5 text-sm">
                          {missing.map((d) => <li key={d.name}>{d.name}</li>)}
                        </ul>
                      )}
                    </td>
                    <td className="px-5 py-4 text-right">
                      {claim && <ClaimPackButton caseId={caseId} asset={a} compact />}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
