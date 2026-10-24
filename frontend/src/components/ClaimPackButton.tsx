import { useState } from "react";
import { downloadClaimPack } from "../api";
import { claimPackFilename } from "../labels";
import type { Asset } from "../types";

export default function ClaimPackButton({ caseId, asset, compact = false }: { caseId: string; asset: Asset; compact?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadClaimPack(caseId, asset.id, claimPackFilename(asset.institution, asset.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={compact ? "" : "flex items-center gap-4"}>
      <button
        onClick={download}
        disabled={busy}
        className={`whitespace-nowrap rounded-lg bg-accent font-semibold text-page transition hover:brightness-110 disabled:opacity-60 ${compact ? "px-4 py-2" : "px-6 py-3 text-lg"}`}
      >
        {busy ? "Downloading…" : "Download claim pack"}
      </button>
      {error && <div className={`text-sm text-red-300 ${compact ? "mt-1 max-w-56" : ""}`}>{error}</div>}
    </div>
  );
}
