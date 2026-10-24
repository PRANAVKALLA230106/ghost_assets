// Read-only derivations from the store. Selectors passed to useGhostStore must return primitives or
// existing references (zustand v5 re-renders forever on a fresh object per call).
import type { GhostData } from "./store";
import type { ProgressData } from "./types";

/** Total value found so far: the final number once `done` arrives, else the live sum of assets. */
export const selectFoundValue = (s: GhostData) =>
  s.done?.total_value ?? Object.values(s.assets).reduce((sum, a) => sum + (a.est_value ?? 0), 0);

export const selectKnownValue = (s: GhostData) =>
  s.done?.known_value ??
  Object.values(s.assets).reduce((sum, a) => sum + (a.known_to_family ? (a.est_value ?? 0) : 0), 0);

export const selectAssetCount = (s: GhostData) => Object.keys(s.assets).length;

/**
 * Messages scanned / financial, from progress events. Handles both the real pipeline's stages
 * ("scan", "extract:<source>") and the fake replay's ("triage", "triage_done").
 */
export function scanCounters(counters: Record<string, ProgressData>): { scanned: number; financial: number } {
  const scanned = Math.max(counters.scan?.done ?? 0, counters.triage?.done ?? 0);
  const extractAll = counters["extract:all"]?.total ?? 0;
  const extractPerSource = Object.entries(counters)
    .filter(([stage]) => stage.startsWith("extract:") && stage !== "extract:all")
    .reduce((sum, [, p]) => sum + p.total, 0);
  const financial = Math.max(counters.triage_done?.done ?? 0, extractAll, extractPerSource);
  return { scanned, financial };
}
