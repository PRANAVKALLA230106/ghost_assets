import { useEffect, useRef } from "react";
import { useGhostStore } from "../store";

export default function AgentTrace() {
  const steps = useGhostStore((s) => s.agentSteps);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [steps.length]);

  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-lg bg-card">
      <div className="border-b border-page px-4 py-2 text-sm uppercase tracking-wide text-muted">Agent trace</div>
      <div ref={scroller} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {steps.length === 0 && <div className="text-muted">Waiting for the agent…</div>}
        {steps.map((step, i) => (
          <div key={i} className="animate-[fadein_400ms_ease-out]">
            <span className="inline-block rounded-full bg-accent px-3 py-0.5 font-mono text-sm font-semibold text-page">
              {step.tool}
            </span>
            <div className="mt-1.5 text-lg leading-snug">{step.thought}</div>
            {step.result_summary && <div className="mt-0.5 text-base text-muted">{step.result_summary}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
