import type { AssetDetail, ConfidenceDetail, EventType, GhostEvent } from "./types";

// The ONLY place the backend URL lives.
export const API_BASE = "http://localhost:8080"; // matches `uvicorn app:app --port 8080 --reload` (run from backend/)

export interface CreateCaseBody {
  deceased_name: string;
  date_of_death: string; // ISO date
  data_dir: string;
  documents_have?: string[]; // matches Case.documents_have
  known_assets?: string[]; // free text the family already knows about, e.g. "SBI savings account ending 8812"
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: HTTP ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const createCase = (body: CreateCaseBody) => post<{ case_id: string }>("/cases", body);

export interface UploadCaseBody {
  deceased_name: string;
  date_of_death: string; // ISO date
  documents_have: string[];
  known_assets: string[];
  sms: File;
  email: File;
  ais: File;
  photos: File[];
}

/** Uploads the heir's files as multipart/form-data; the backend saves them and starts the real agent. */
export async function uploadCase(body: UploadCaseBody): Promise<{ case_id: string }> {
  const form = new FormData();
  form.append("deceased_name", body.deceased_name);
  form.append("date_of_death", body.date_of_death);
  for (const d of body.documents_have) form.append("documents_have", d);
  for (const k of body.known_assets) form.append("known_assets", k);
  form.append("sms", body.sms);
  form.append("email", body.email);
  form.append("ais", body.ais);
  for (const p of body.photos) form.append("photos", p);
  const res = await fetch(`${API_BASE}/cases/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`POST /cases/upload failed: HTTP ${res.status} ${await res.text()}`);
  return res.json() as Promise<{ case_id: string }>;
}

export const runCase = (caseId: string) =>
  post<{ case_id: string; status: string }>(`/cases/${caseId}/run`);

export const postAnswer = (caseId: string, questionId: string, answer: string) =>
  post<unknown>(`/cases/${caseId}/answers`, { question_id: questionId, answer });

export async function getHealth(): Promise<{ status: string; fake_events: boolean }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ status: string; fake_events: boolean }>;
}

export async function getAssetDetail(caseId: string, assetId: string): Promise<AssetDetail> {
  const res = await fetch(`${API_BASE}/cases/${caseId}/assets/${assetId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<AssetDetail>;
}

/** Fetches the .docx and saves it. Throws with the server's reason (e.g. pack not generated yet). */
/** GET /cases/{id}/confidence: breakdown for every asset, keyed by asset id. */
export async function getConfidence(caseId: string): Promise<Record<string, ConfidenceDetail>> {
  const res = await fetch(`${API_BASE}/cases/${caseId}/confidence`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function downloadClaimPack(caseId: string, assetId: string, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}/cases/${caseId}/assets/${assetId}/claimpack.docx`);
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail as string).catch(() => `HTTP ${res.status}`);
    throw new Error(detail);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const SSE_EVENT_TYPES: EventType[] = [
  "progress", "clue", "asset", "agent_step", "question", "claim", "done", "error",
];

/**
 * Opens the case's SSE stream. The backend sends named events (`event: <type>`, `data: <payload>`),
 * so we listen per type and rebuild {type, data}. Closes itself after `done` or a server `error`.
 * Returns a function that closes the stream.
 */
export function openEventStream(
  caseId: string,
  onEvent: (event: GhostEvent) => void,
  onConnection: (state: "open" | "reconnecting" | "closed") => void,
): () => void {
  const es = new EventSource(`${API_BASE}/cases/${caseId}/events`);
  const close = () => {
    es.close();
    onConnection("closed");
  };

  es.onopen = () => onConnection("open");

  for (const type of SSE_EVENT_TYPES) {
    es.addEventListener(type, (e) => {
      // "error" is also EventSource's own connection-error event, which has no data.
      if (!(e instanceof MessageEvent) || typeof e.data !== "string") {
        if (type === "error") onConnection(es.readyState === EventSource.CLOSED ? "closed" : "reconnecting");
        return;
      }
      onEvent({ type, data: JSON.parse(e.data) } as GhostEvent);
      if (type === "done" || type === "error") close();
    });
  }

  return close;
}
