import { useCallback, useEffect, useState } from "react";
import { Outlet, useLocation, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { API_BASE, getHealth, openEventStream } from "../api";
import { applyEvent, useGhostStore } from "../store";
import AssetDrawer from "../components/AssetDrawer";
import QuestionModal from "../components/QuestionModal";

export type Connection = "connecting" | "open" | "reconnecting" | "closed";

export interface CaseContext {
  caseId: string;
  deceasedName?: string;
  connection: Connection;
  openAsset: (assetId: string) => void;
}

export const useCaseContext = () => useOutletContext<CaseContext>();

/** The name comes from screen 1 via router state; remember it so a refresh keeps the header. */
function useDeceasedName(caseId: string): string | undefined {
  const fromNav = (useLocation().state as { deceasedName?: string } | null)?.deceasedName;
  const key = `ghost:case:${caseId}:name`;
  try {
    if (fromNav) sessionStorage.setItem(key, fromNav);
    return fromNav ?? sessionStorage.getItem(key) ?? undefined;
  } catch {
    return fromNav;
  }
}

/**
 * Parent route of every /case/:id screen. Owns the SSE stream so switching between the live map and
 * the claims table never drops events, and hosts what every screen shares: the question modal and the
 * asset drawer (opened with ?asset=<id>, so it works from any screen and survives a refresh).
 */
export default function CaseLayout() {
  const { id = "" } = useParams<{ id: string }>();
  const deceasedName = useDeceasedName(id);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [params, setParams] = useSearchParams();
  const errors = useGhostStore((s) => s.errors);
  const [fakeBackend, setFakeBackend] = useState(false);

  // The case view only ever shows the live SSE stream; make it loud if that backend is replaying fake events.
  useEffect(() => {
    getHealth().then((h) => setFakeBackend(h.fake_events)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!id) return;
    applyEvent({ type: "reset" });
    // The backend's event queue has a single consumer. Deferring the connect means React StrictMode's
    // throwaway first mount never opens a stream that could swallow events.
    let close: (() => void) | null = null;
    const t = window.setTimeout(() => {
      close = openEventStream(id, applyEvent, setConnection);
    }, 0);
    return () => {
      window.clearTimeout(t);
      close?.();
    };
  }, [id]);

  const selectedAsset = params.get("asset");
  const openAsset = useCallback(
    (assetId: string) => setParams((p) => { p.set("asset", assetId); return p; }),
    [setParams],
  );
  const closeAsset = useCallback(
    () => setParams((p) => { p.delete("asset"); return p; }),
    [setParams],
  );

  return (
    <>
      <Outlet context={{ caseId: id, deceasedName, connection, openAsset } satisfies CaseContext} />

      {fakeBackend && (
        <div className="fixed inset-x-0 top-0 z-50 bg-red-700 px-4 py-2 text-center text-sm font-semibold text-white">
          The backend at {API_BASE} has FAKE_EVENTS=1: this stream is a replay, not the real pipeline.
        </div>
      )}

      {errors.length > 0 && (
        <div className="fixed right-5 top-5 z-50 max-w-lg space-y-2">
          {errors.map((m, i) => (
            <p key={i} className="rounded bg-card px-4 py-3 text-sm text-red-300 shadow-lg">{m}</p>
          ))}
        </div>
      )}

      {selectedAsset && <AssetDrawer caseId={id} assetId={selectedAsset} onClose={closeAsset} />}
      <QuestionModal caseId={id} />
    </>
  );
}
