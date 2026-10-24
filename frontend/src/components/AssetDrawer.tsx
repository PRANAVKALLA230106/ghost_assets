import { useEffect, useState, type ReactNode } from "react";
import { getAssetDetail } from "../api";
import { useGhostStore } from "../store";
import { formatINR } from "../format";
import { ASSET_TYPE_LABEL, STATUS_LABEL, claimPathLabel, confidenceLabel } from "../labels";
import type { AssetDetail, EvidenceQuote } from "../types";
import ClaimPackButton from "./ClaimPackButton";
import ConfidenceBreakdown from "./ConfidenceBreakdown";

type Load =
  | { state: "loading" }
  | { state: "ok"; detail: AssetDetail }
  | { state: "fallback"; reason: string }; // backend has no record (e.g. fake-event mode): use the store

/** Escapes regex specials and lets any run of whitespace match any other, like the backend's grounding check. */
function quotePattern(quote: string): RegExp | null {
  const words = quote.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return null;
  return new RegExp(words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+"), "i");
}

function Highlighted({ text, quote }: { text: string; quote: string }) {
  const m = quotePattern(quote)?.exec(text);
  if (!m) {
    return (
      <>
        <p className="whitespace-pre-wrap text-muted">{text}</p>
        <p className="mt-2"><mark className="rounded bg-accent/25 px-1 text-ink">{quote}</mark></p>
      </>
    );
  }
  return (
    <p className="whitespace-pre-wrap text-muted">
      {text.slice(0, m.index)}
      <mark className="rounded bg-accent/25 px-1 font-medium text-ink ring-1 ring-accent/60">{m[0]}</mark>
      {text.slice(m.index + m[0].length)}
    </p>
  );
}

function EvidenceCard({ q }: { q: EvidenceQuote }) {
  const isPortal = q.evidence_id.startsWith("portal_");
  return (
    <li className="rounded-lg border border-muted/15 bg-page p-4">
      <div className="mb-2 flex items-center justify-between gap-3 text-xs uppercase tracking-wide text-muted">
        <span>
          {isPortal ? "Portal record" : q.source ?? "message"}
          {q.sender && <> · <span className="normal-case">{q.sender}</span></>}
        </span>
        <span className="font-mono normal-case">{q.date ?? ""} · {q.evidence_id}</span>
      </div>
      {q.text ? <Highlighted text={q.text} quote={q.quote} /> : (
        <p><mark className="rounded bg-accent/25 px-1 text-ink">{q.quote}</mark></p>
      )}
    </li>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-lg">{children}</dd>
    </div>
  );
}

export default function AssetDrawer({ caseId, assetId, onClose }: { caseId: string; assetId: string; onClose: () => void }) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const storeAsset = useGhostStore((s) => s.assets[assetId]);
  const storeClaim = useGhostStore((s) => s.claims[assetId]);
  const clues = useGhostStore((s) => s.clues);

  useEffect(() => {
    let cancelled = false;
    setLoad({ state: "loading" });
    getAssetDetail(caseId, assetId)
      .then((detail) => !cancelled && setLoad({ state: "ok", detail }))
      .catch((err) => !cancelled && setLoad({ state: "fallback", reason: String(err.message ?? err) }));
    return () => { cancelled = true; };
    // Refetch when the asset or its claim changes (e.g. after the family answers a question).
  }, [caseId, assetId, storeAsset, storeClaim]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const asset = load.state === "ok" ? load.detail.asset : storeAsset;
  const claim = (load.state === "ok" ? load.detail.claim : null) ?? storeClaim ?? null;
  const quotes: EvidenceQuote[] =
    load.state === "ok"
      ? load.detail.quotes
      : clues
          .filter((c) => asset?.clue_ids.includes(c.id))
          .map((c) => ({ evidence_id: c.evidence_id, date: c.date, quote: c.quote, source: null, sender: null, text: null }));

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <aside className="relative flex h-full w-[720px] max-w-full animate-[drawerin_250ms_ease-out] flex-col bg-card shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-page px-8 py-6">
          <div>
            <div className="text-sm uppercase tracking-wide text-muted">
              {asset ? ASSET_TYPE_LABEL[asset.asset_type] : "Asset"}
            </div>
            <h2 className="text-3xl font-semibold">{asset?.institution ?? assetId}</h2>
          </div>
          <button onClick={onClose} className="rounded px-3 py-1 text-2xl text-muted hover:text-accent" aria-label="Close">
            ×
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
          {load.state === "loading" && !asset && <p className="text-muted">Loading…</p>}
          {!asset && load.state !== "loading" && <p className="text-red-300">Asset {assetId} not found.</p>}

          {asset && (
            <>
              <div className="text-5xl font-bold text-accent">
                {asset.est_value != null ? formatINR(asset.est_value) : "Value unknown"}
              </div>
              {asset.value_basis && <div className="mt-1 text-muted">Based on {asset.value_basis}</div>}

              <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4">
                <Field label="Identifier"><span className="font-mono">{asset.identifier ?? "—"}</span></Field>
                <Field label="Type">{ASSET_TYPE_LABEL[asset.asset_type]}</Field>
                <Field label="Confidence">
                  {confidenceLabel(asset.confidence)} <span className="text-sm text-muted">({Math.round(asset.confidence * 100)}%)</span>
                </Field>
                <Field label="Status">{STATUS_LABEL[asset.status]}</Field>
                <Field label="Claim path">{claim ? claimPathLabel(claim.path) : <span className="text-muted">Not decided yet</span>}</Field>
                <Field label="Submit to">{claim?.where ?? "—"}</Field>
              </dl>

              <div className="mt-6">
                <ClaimPackButton caseId={caseId} asset={asset} />
              </div>

              {load.state === "ok" && load.detail.confidence && <ConfidenceBreakdown detail={load.detail.confidence} />}

              <h3 className="mt-8 text-sm uppercase tracking-wide text-muted">
                Evidence ({quotes.length})
              </h3>
              {load.state === "fallback" && (
                <p className="mt-1 text-xs text-muted">
                  Original messages unavailable ({load.reason}); showing the extracted quotes.
                </p>
              )}
              <ul className="mt-3 space-y-3">
                {quotes.map((q, i) => <EvidenceCard key={`${q.evidence_id}-${i}`} q={q} />)}
              </ul>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
