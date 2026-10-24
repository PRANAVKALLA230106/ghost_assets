// Mirrors backend/models.py and the SSE contract in CLAUDE.md. Keep in sync with the backend.

export type AssetType =
  | "savings_account" | "fixed_deposit" | "life_insurance" | "mutual_fund"
  | "shares" | "provident_fund" | "post_office" | "other";

export type AmountKind =
  | "balance" | "principal" | "maturity_value" | "sum_assured" | "premium"
  | "sip_instalment" | "dividend" | "interest" | "credit" | "debit" | "market_value" | "unknown";

export type Status =
  | "active" | "dormant" | "transferred_dea" | "transferred_iepf" | "transferred_scwf" | "unknown";

export type Nominee = "yes" | "no" | "unknown";

export interface Evidence {
  id: string; // sms_0001 | email_001 | ais_01 | photo_<stem>
  source: "sms" | "email" | "ais" | "photo";
  sender: string;
  timestamp: string | null;
  text: string;
  path: string | null;
  is_financial: boolean;
}

export interface Clue {
  id: string; // cl_0001
  evidence_id: string;
  institution_raw: string;
  institution: string | null;
  asset_type: AssetType;
  identifier: string | null;
  amount: number | null;
  amount_kind: AmountKind;
  date: string | null;
  nominee: string | null; // name, "not registered", or null if not mentioned
  quote: string;
}

export interface Asset {
  id: string;
  institution: string;
  asset_type: AssetType;
  identifier: string | null;
  est_value: number | null;
  value_basis?: string | null; // optional because fake_events.jsonl omits it
  confidence: number; // 0..1
  last_activity: string | null;
  status: Status;
  nominee: Nominee;
  known_to_family: boolean;
  clue_ids: string[];
}

export interface ClaimDocument {
  name: string;
  have: boolean;
}

export type ClaimPath =
  | "nominee" | "simplified_no_nominee" | "standard_succession" | "dea_claim_via_bank"
  | "insurance_death_claim" | "transmission" | "iepf_refund" | "epf_claim" | "needs_nominee_answer";

export interface Claim {
  asset_id: string;
  path: ClaimPath;
  where: string;
  documents: ClaimDocument[];
  deadline_note: string | null;
}

export interface Case {
  id: string;
  deceased_name: string;
  date_of_death: string;
  data_dir: string;
  documents_have: string[];
  known_assets: string[];
}

// ---- GET /cases/{id}/assets/{asset_id} ----

export interface EvidenceQuote {
  evidence_id: string; // or portal_<NAME> for a portal record
  date: string | null;
  quote: string;
  source: Evidence["source"] | null; // null for portal records
  sender: string | null;
  text: string | null; // the original message
}

export interface AssetDetail {
  asset: Asset;
  claim: Claim | null;
  quotes: EvidenceQuote[];
  has_claim_pack: boolean;
}

// ---- SSE events: {"type": <name>, "data": <payload>} ----

export interface ProgressData { stage: string; done: number; total: number }
export interface AgentStepData {
  thought: string;
  tool: string;
  args: Record<string, unknown>;
  result_summary: string;
}
export interface QuestionData { id: string; text: string; options: string[] }
export interface DoneData { total_value: number; known_value: number; asset_count: number }
export interface ErrorData { message: string }

export type GhostEvent =
  | { type: "progress"; data: ProgressData }
  | { type: "clue"; data: Clue }
  | { type: "asset"; data: Asset }
  | { type: "agent_step"; data: AgentStepData }
  | { type: "question"; data: QuestionData }
  | { type: "claim"; data: Claim }
  | { type: "done"; data: DoneData }
  | { type: "error"; data: ErrorData };

export type EventType = GhostEvent["type"];
