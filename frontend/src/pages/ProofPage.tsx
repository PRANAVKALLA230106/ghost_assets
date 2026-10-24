import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getConfidence } from "../api";
import { useGhostStore } from "../store";
import { formatINR } from "../format";
import { ASSET_TYPE_LABEL, LEVEL_COLOR, PROOF_SOURCE_LABEL, confidenceLabel } from "../labels";
import type { Asset, Clue, ConfidenceDetail, ProofSource } from "../types";
import { ConfidenceGauge } from "../components/ConfidenceBreakdown";
import { useCaseContext } from "./CaseLayout";

const SOURCES: ProofSource[] = ["sms", "email", "ais", "photo", "portal"];

/** Used when the backend has no /confidence route (e.g. fake-event replay): sources from the store's clues. */
function fallbackDetail(a: Asset, clues: Clue[]): ConfidenceDetail {
  const ids = new Set(a.clue_ids);
  const sources: Partial<Record<ProofSource, number>> = {};
  let n = 0;
  for (const c of clues) {
    if (!ids.has(c.id)) continue;
    n += 1;
    const src = c.evidence_id.split("_")[0] as ProofSource;
    sources[src] = (sources[src] ?? 0) + 1;
  }
  if (a.value_basis?.includes("portal")) sources.portal = 1;
  return { score: a.confidence, level: confidenceLabel(a.confidence), summary: "", factors: [], sources, evidence_count: n, verified_quotes: n };
}

function SourceDot({ count, color }: { count: number | undefined; color: string }) {
  if (!count) return <span className="inline-block h-3 w-3 rounded-full border border-muted/30" aria-label="not found" />;
  const size = Math.min(34, 16 + Math.log2(count + 1) * 4);
  return (
    <span
      className="inline-flex items-center justify-center rounded-full text-xs font-bold text-page"
      style={{ width: size, height: size, background: color }}
      title={`${count} item${count === 1 ? "" : "s"}`}
    >
      {count > 1 ? (count > 99 ? "99+" : count) : "✓"}
    </span>
  );
}

function Tile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-card px-5 py-4">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-3xl font-bold">{children}</div>
    </div>
  );
}

/** Screen 3: for every asset, which independent sources prove it and how sure we are. */
export default function ProofPage() {
  const { caseId, deceasedName, openAsset } = useCaseContext();
  const assets = useGhostStore((s) => s.assets);
  const clues = useGhostStore((s) => s.clues);
  const eventCount = useGhostStore((s) => s.eventCount);
  const [details, setDetails] = useState<Record<string, ConfidenceDetail> | null>(null);

  // Refetch shortly after the stream goes quiet, so scores follow portal hits and family answers.
  useEffect(() => {
    const t = window.setTimeout(() => {
      getConfidence(caseId).then(setDetails).catch(() => setDetails(null));
    }, 600);
    return () => window.clearTimeout(t);
  }, [caseId, eventCount]);

  const rows = useMemo(
    () =>
      Object.values(assets)
        .map((a) => ({ a, d: details?.[a.id] ?? fallbackDetail(a, clues) }))
        .sort((x, y) => y.d.score - x.d.score || (y.a.est_value ?? 0) - (x.a.est_value ?? 0)),
    [assets, details, clues],
  );

  const counts = { High: 0, Medium: 0, Low: 0 };
  rows.forEach(({ d }) => (counts[d.level] += 1));
  const verified = rows.reduce((s, { d }) => s + d.verified_quotes, 0);
  const official = rows.filter(({ a, d }) => d.sources.ais || d.sources.portal || a.known_to_family).length;
  const avg = rows.length ? rows.reduce((s, { d }) => s + d.score, 0) / rows.length : 0;

  return (
    <div className="min-h-screen bg-page px-10 py-8 text-ink">
      <div className="flex gap-5 text-muted">
        <Link to={`/case/${caseId}`} className="hover:text-accent">← Live map</Link>
        <Link to={`/case/${caseId}/claims`} className="hover:text-accent">Claims →</Link>
      </div>
      <h1 className="mt-2 text-4xl font-semibold">
        How sure are we?{deceasedName && <span className="text-muted"> · {deceasedName}</span>}
      </h1>
      <p className="mt-1 max-w-3xl text-lg text-muted">
        Every asset is backed by evidence the AI quoted word-for-word from the original messages. The more independent
        sources agree, the surer we are.
      </p>

      {rows.length === 0 ? (
        <p className="mt-10 text-muted">No assets yet. They appear here as the agent finds them.</p>
      ) : (
        <>
          <div className="mt-6 grid grid-cols-[auto_1fr_1fr_1fr] items-stretch gap-4">
            <div className="flex items-center gap-4 rounded-lg bg-card px-5 py-3">
              <ConfidenceGauge score={avg} level={confidenceLabel(avg)} size={96} />
              <div>
                <div className="text-xs uppercase tracking-wide text-muted">Average confidence</div>
                <div className="mt-2 flex h-3 w-48 overflow-hidden rounded-full">
                  {(["High", "Medium", "Low"] as const).map((l) =>
                    counts[l] ? <div key={l} style={{ flex: counts[l], background: LEVEL_COLOR[l] }} /> : null,
                  )}
                </div>
                <div className="mt-2 flex gap-3 text-sm">
                  {(["High", "Medium", "Low"] as const).map((l) => (
                    <span key={l}><span style={{ color: LEVEL_COLOR[l] }}>●</span> {counts[l]} {l}</span>
                  ))}
                </div>
              </div>
            </div>
            <Tile label="Assets found">{rows.length}</Tile>
            <Tile label="Quotes verified word-for-word"><span className="text-[#7bd88f]">{verified}</span></Tile>
            <Tile label="Backed by an official record">{official} <span className="text-lg text-muted">of {rows.length}</span></Tile>
          </div>

          <div className="mt-6 overflow-hidden rounded-lg bg-card">
            <table className="w-full text-left">
              <thead className="border-b border-page text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-5 py-3 font-medium">Asset</th>
                  <th className="px-3 py-3 text-right font-medium">Value</th>
                  {SOURCES.map((s) => <th key={s} className="px-3 py-3 text-center font-medium">{PROOF_SOURCE_LABEL[s]}</th>)}
                  <th className="px-3 py-3 text-center font-medium">Family</th>
                  <th className="w-72 px-5 py-3 font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ a, d }) => {
                  const color = LEVEL_COLOR[d.level];
                  return (
                    <tr
                      key={a.id}
                      onClick={() => openAsset(a.id)}
                      className="cursor-pointer border-b border-page/60 last:border-0 hover:bg-page/40"
                    >
                      <td className="px-5 py-3">
                        <div className="font-semibold">{a.institution}</div>
                        <div className="text-sm text-muted">
                          {ASSET_TYPE_LABEL[a.asset_type]}
                          {a.identifier && <> · <span className="font-mono">{a.identifier}</span></>}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right font-semibold tabular-nums text-accent">
                        {a.est_value != null ? formatINR(a.est_value) : "—"}
                      </td>
                      {SOURCES.map((s) => (
                        <td key={s} className="px-3 py-3 text-center"><SourceDot count={d.sources[s]} color={color} /></td>
                      ))}
                      <td className="px-3 py-3 text-center"><SourceDot count={a.known_to_family ? 1 : 0} color={color} /></td>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted/15">
                            <div className="h-full rounded-full" style={{ width: `${d.score * 100}%`, background: color, transition: "width 600ms ease-out" }} />
                          </div>
                          <span className="w-28 shrink-0 text-right text-sm font-semibold tabular-nums" style={{ color }}>
                            {Math.round(d.score * 100)}% {d.level}
                          </span>
                        </div>
                        {d.summary && <div className="mt-1 line-clamp-1 text-xs text-muted">{d.summary}</div>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <details className="mt-5 rounded-lg bg-card px-5 py-4 text-sm">
            <summary className="cursor-pointer font-semibold">How the score works (100 points)</summary>
            <ul className="mt-3 grid grid-cols-2 gap-x-8 gap-y-2 text-muted">
              <li><b className="text-ink">Account number · 25</b>: a 4+ digit number ties every message to one specific account.</li>
              <li><b className="text-ink">Independent sources · 30</b>: SMS, email, tax record, photo, government portal. 10 each, up to 3.</li>
              <li><b className="text-ink">Official record · 20</b>: RBI UDGAM / IEPF record, Income Tax AIS, or the family confirms it. A photo of the original document gets 12.</li>
              <li><b className="text-ink">Repeated evidence · 10</b>: 5+ separate messages = 10, 2–4 = 6, 1 = 3.</li>
              <li><b className="text-ink">Still alive · 15</b>: activity in the last 2 years, or a long silence explained by a portal record (money moved to RBI / IEPF).</li>
              <li><b className="text-ink">Before any of this</b>: every clue must quote the original message exactly, with its account number and amount, or it is discarded.</li>
            </ul>
          </details>
          <p className="mt-3 text-sm text-muted">Click any row to see the original messages behind it.</p>
        </>
      )}
    </div>
  );
}
