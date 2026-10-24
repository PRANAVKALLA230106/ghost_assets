import { create } from "zustand";
import type { AgentStepData, Asset, Claim, Clue, DoneData, GhostEvent, ProgressData, QuestionData } from "./types";

// Frontend-only event that clears the store (before a replay or a new run). The backend never sends it.
export type ResetEvent = { type: "reset" };
export type StoreEvent = GhostEvent | ResetEvent;

export interface GhostData {
  counters: Record<string, ProgressData>; // latest progress event per stage
  clues: Clue[];
  assets: Record<string, Asset>; // keyed by asset id
  agentSteps: AgentStepData[];
  questions: QuestionData[];
  claims: Record<string, Claim>; // keyed by asset_id; a later claim for the same asset replaces it
  done: DoneData | null;
  errors: string[];
  eventCount: number;
}

export interface GhostStore extends GhostData {
  applyEvent: (event: StoreEvent) => void;
}

const initialData = (): GhostData => ({
  counters: {},
  clues: [],
  assets: {},
  agentSteps: [],
  questions: [],
  claims: {},
  done: null,
  errors: [],
  eventCount: 0,
});

function reduce(s: GhostData, e: StoreEvent): Partial<GhostData> {
  if (e.type === "reset") return initialData();
  const eventCount = s.eventCount + 1;
  switch (e.type) {
    case "progress":
      return { eventCount, counters: { ...s.counters, [e.data.stage]: e.data } };
    case "clue":
      // Same clue id again (e.g. institution filled in later) replaces the old one.
      return s.clues.some((c) => c.id === e.data.id)
        ? { eventCount, clues: s.clues.map((c) => (c.id === e.data.id ? e.data : c)) }
        : { eventCount, clues: [...s.clues, e.data] };
    case "asset":
      return { eventCount, assets: { ...s.assets, [e.data.id]: e.data } };
    case "agent_step":
      return { eventCount, agentSteps: [...s.agentSteps, e.data] };
    case "question":
      return s.questions.some((q) => q.id === e.data.id)
        ? { eventCount }
        : { eventCount, questions: [...s.questions, e.data] };
    case "claim":
      return { eventCount, claims: { ...s.claims, [e.data.asset_id]: e.data } };
    case "done":
      return { eventCount, done: e.data };
    case "error":
      return { eventCount, errors: [...s.errors, e.data.message] };
    default:
      console.warn("[store] unknown event", e);
      return { eventCount };
  }
}

// applyEvent is the ONLY way state changes. Components read state; nothing else calls set().
export const useGhostStore = create<GhostStore>()((set) => ({
  ...initialData(),
  applyEvent: (event) => set((s) => reduce(s, event)),
}));

export const applyEvent = (event: StoreEvent) => useGhostStore.getState().applyEvent(event);
