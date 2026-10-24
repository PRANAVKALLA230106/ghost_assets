import AgentTrace from "../components/AgentTrace";
import AssetGraph from "../components/AssetGraph";
import CountersPanel from "../components/CountersPanel";
import DoneBanner from "../components/DoneBanner";
import TopBanner from "../components/TopBanner";
import { useCaseContext } from "./CaseLayout";

/** Screen 2: the live map. The stream, question modal and asset drawer live in CaseLayout. */
export default function CasePage() {
  const { caseId, deceasedName, connection, openAsset } = useCaseContext();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-page text-ink">
      <TopBanner deceasedName={deceasedName} caseId={caseId} />
      <DoneBanner deceasedName={deceasedName} />

      <main className="grid min-h-0 flex-1 grid-cols-[480px_1fr] gap-5 p-5">
        <aside className="flex min-h-0 flex-col gap-4">
          <CountersPanel />
          <AgentTrace />
          <div className="text-xs text-muted">
            Case {caseId} · stream {connection}
          </div>
        </aside>
        <section className="min-h-0">
          <AssetGraph onAssetClick={openAsset} />
        </section>
      </main>
    </div>
  );
}
