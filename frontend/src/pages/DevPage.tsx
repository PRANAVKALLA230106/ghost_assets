import { useEffect, useRef, useState } from "react";
import { applyEvent, useGhostStore } from "../store";
import type { GhostEvent } from "../types";

const REPLAY_MS = 200;

async function loadFakeEvents(): Promise<GhostEvent[]> {
  const res = await fetch("/fake_events.jsonl");
  if (!res.ok) throw new Error(`fake_events.jsonl: HTTP ${res.status}`);
  const text = await res.text();
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as GhostEvent);
}

export default function DevPage() {
  const { applyEvent: _applyEvent, ...data } = useGhostStore();
  const [status, setStatus] = useState("idle");
  const timer = useRef<number | null>(null);

  const stop = () => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
  };
  useEffect(() => stop, []);

  const replay = async () => {
    stop();
    let events: GhostEvent[];
    try {
      events = await loadFakeEvents();
    } catch (err) {
      setStatus(String(err));
      return;
    }
    applyEvent({ type: "reset" });
    let i = 0;
    setStatus(`replaying 0/${events.length}`);
    timer.current = window.setInterval(() => {
      if (i >= events.length) {
        stop();
        setStatus(`finished ${events.length} events`);
        return;
      }
      applyEvent(events[i++]);
      setStatus(`replaying ${i}/${events.length}`);
    }, REPLAY_MS);
  };

  const summary: [string, string | number][] = [
    ["events", data.eventCount],
    ["clues", data.clues.length],
    ["assets", Object.keys(data.assets).length],
    ["agent steps", data.agentSteps.length],
    ["questions", data.questions.length],
    ["claims", Object.keys(data.claims).length],
    ["done", data.done ? "yes" : "no"],
  ];

  return (
    <div className="min-h-screen bg-page p-6 text-ink">
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <h1 className="text-xl font-semibold text-accent">Dev: event replay</h1>
        <button
          onClick={replay}
          className="rounded bg-accent px-4 py-2 font-medium text-page hover:opacity-90"
        >
          Replay fake_events.jsonl
        </button>
        <span className="text-sm text-muted">{status}</span>
      </div>
      <div className="mb-4 flex flex-wrap gap-3 text-sm">
        {summary.map(([label, value]) => (
          <div key={label} className="rounded bg-card px-3 py-2">
            <span className="text-muted">{label}: </span>
            <span className="text-accent">{value}</span>
          </div>
        ))}
      </div>
      <pre className="overflow-auto rounded bg-card p-4 text-xs leading-relaxed text-ink">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
