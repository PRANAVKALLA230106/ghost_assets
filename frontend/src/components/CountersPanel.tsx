import { useMemo } from "react";
import { useGhostStore } from "../store";
import { scanCounters, selectAssetCount } from "../selectors";
import AnimatedNumber from "./AnimatedNumber";

const plain = (n: number) => Math.round(n).toLocaleString("en-IN");

export default function CountersPanel() {
  const counters = useGhostStore((s) => s.counters);
  const clues = useGhostStore((s) => s.clues.length);
  const assets = useGhostStore(selectAssetCount);
  const { scanned, financial } = useMemo(() => scanCounters(counters), [counters]);

  const tiles: [string, number][] = [
    ["Messages scanned", scanned],
    ["Financial", financial],
    ["Clues", clues],
    ["Assets", assets],
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {tiles.map(([label, value]) => (
        <div key={label} className="rounded-lg bg-card px-4 py-3">
          <div className="text-4xl font-semibold text-accent">
            <AnimatedNumber value={value} format={plain} durationMs={400} />
          </div>
          <div className="text-sm uppercase tracking-wide text-muted">{label}</div>
        </div>
      ))}
    </div>
  );
}
