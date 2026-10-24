import { LEVEL_COLOR } from "../labels";
import type { ConfidenceDetail } from "../types";

/** Circular gauge: the score as an arc, the % in the middle. */
export function ConfidenceGauge({ score, level, size = 120 }: { score: number; level: ConfidenceDetail["level"]; size?: number }) {
  const r = size / 2 - 9;
  const c = 2 * Math.PI * r;
  const color = LEVEL_COLOR[level];
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${level} confidence, ${Math.round(score * 100)}%`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeOpacity={0.12} strokeWidth={9} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={9} strokeLinecap="round"
        strokeDasharray={`${c * score} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dasharray 700ms ease-out" }}
      />
      <text x="50%" y="47%" textAnchor="middle" dominantBaseline="middle" fill="currentColor" fontSize={size * 0.24} fontWeight={700}>
        {Math.round(score * 100)}%
      </text>
      <text x="50%" y="68%" textAnchor="middle" dominantBaseline="middle" fill={color} fontSize={size * 0.11} fontWeight={600}>
        {level.toUpperCase()}
      </text>
    </svg>
  );
}

/** "Why we're sure": gauge, one-line summary, and one bar per factor with its plain-English reason. */
export default function ConfidenceBreakdown({ detail }: { detail: ConfidenceDetail }) {
  const color = LEVEL_COLOR[detail.level];
  return (
    <section className="mt-8 rounded-lg border border-muted/15 bg-page p-5">
      <h3 className="text-sm uppercase tracking-wide text-muted">Why we're sure this exists</h3>
      <div className="mt-3 flex items-center gap-5">
        <ConfidenceGauge score={detail.score} level={detail.level} />
        <p className="text-lg leading-snug">{detail.summary}.</p>
      </div>

      <ul className="mt-5 space-y-3">
        {detail.factors.map((f) => {
          const pct = f.max ? (f.points / f.max) * 100 : 0;
          return (
            <li key={f.key}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="font-semibold">{f.label}</span>
                <span className="tabular-nums text-muted">{Math.round(f.points)} / {f.max}</span>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted/15">
                <div className="h-full rounded-full" style={{ width: `${pct}%`, background: pct >= 75 ? color : pct >= 40 ? "#ffb54d" : "#ff7a6b", transition: "width 600ms ease-out" }} />
              </div>
              <div className="mt-1 text-sm text-muted">{f.detail}</div>
            </li>
          );
        })}
      </ul>

      <p className="mt-5 flex items-center gap-2 border-t border-muted/15 pt-4 text-sm">
        <span className="text-lg text-[#7bd88f]">✓</span>
        All {detail.verified_quotes} quote{detail.verified_quotes === 1 ? "" : "s"} below were checked word-for-word against the
        original message. Anything the AI couldn't prove was thrown away.
      </p>
    </section>
  );
}
