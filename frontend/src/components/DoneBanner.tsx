import { useGhostStore } from "../store";
import { formatLakh } from "../format";

/** Sits in the page flow under the top banner, so the graph shrinks and refits instead of being covered. */
export default function DoneBanner({ deceasedName }: { deceasedName?: string }) {
  const done = useGhostStore((s) => s.done);
  if (!done) return null;

  const first = deceasedName?.trim().split(/\s+/)[0];
  return (
    <div className="animate-[slideup_700ms_ease-out] border-b-2 border-accent bg-card px-10 py-6 text-center">
      <span className="text-4xl leading-tight">
        {first ? `${first}'s family` : "The family"} knew about{" "}
        <span className="text-muted">{formatLakh(done.known_value)}</span>.{" "}
      </span>
      <span className="ml-3 text-6xl font-bold leading-tight">
        {first ?? "They"} left them <span className="text-accent">{formatLakh(done.total_value)}</span>.
      </span>
    </div>
  );
}
