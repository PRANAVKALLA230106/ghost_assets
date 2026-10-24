import { Link } from "react-router-dom";
import { useGhostStore } from "../store";
import { selectFoundValue, selectKnownValue } from "../selectors";
import { formatINR } from "../format";
import AnimatedNumber from "./AnimatedNumber";

export default function TopBanner({ deceasedName, caseId }: { deceasedName?: string; caseId: string }) {
  const found = useGhostStore(selectFoundValue);
  const known = useGhostStore(selectKnownValue);
  const done = useGhostStore((s) => s.done !== null);

  return (
    <header className="flex items-end justify-between gap-8 border-b border-card px-10 py-6">
      <div className="flex items-baseline gap-10">
        <div className="text-7xl font-bold text-accent">
          <AnimatedNumber value={found} format={formatINR} /> <span className="text-5xl">found</span>
        </div>
        <div className="text-3xl text-muted">
          family knew <AnimatedNumber value={known} format={formatINR} />
        </div>
      </div>
      <div className="flex items-end gap-6">
        <div className="text-right">
          <div className="text-2xl font-semibold">Ghost Assets</div>
          {deceasedName && <div className="text-lg text-muted">Estate of {deceasedName}</div>}
        </div>
        <Link
          to={`/case/${caseId}/proof`}
          className="rounded-lg border border-muted/30 px-5 py-3 text-lg font-semibold text-muted transition hover:text-accent"
        >
          Proof
        </Link>
        <Link
          to={`/case/${caseId}/claims`}
          className={`rounded-lg px-5 py-3 text-lg font-semibold transition ${
            done ? "bg-accent text-page hover:brightness-110" : "border border-muted/30 text-muted hover:text-accent"
          }`}
        >
          Claims →
        </Link>
      </div>
    </header>
  );
}
