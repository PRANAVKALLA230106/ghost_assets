import type { AssetType, ClaimPath, Status } from "./types";

export const ASSET_TYPE_LABEL: Record<AssetType, string> = {
  savings_account: "Savings account",
  fixed_deposit: "Fixed deposit",
  life_insurance: "Life insurance",
  mutual_fund: "Mutual fund",
  shares: "Shares",
  provident_fund: "Provident fund",
  post_office: "Post office scheme",
  other: "Other",
};

export const STATUS_LABEL: Record<Status, string> = {
  active: "Active",
  dormant: "Dormant",
  transferred_dea: "Moved to RBI DEA fund",
  transferred_iepf: "Moved to IEPF",
  transferred_scwf: "Moved to Senior Citizens' Welfare Fund",
  unknown: "Unknown",
};

export const CLAIM_PATH_LABEL: Record<ClaimPath, string> = {
  nominee: "Nominee claim",
  simplified_no_nominee: "Simplified claim (no nominee)",
  standard_succession: "Succession certificate",
  dea_claim_via_bank: "DEA claim via the bank",
  insurance_death_claim: "Insurance death claim",
  transmission: "Transmission",
  iepf_refund: "IEPF refund (Form IEPF-5)",
  epf_claim: "EPF claim",
  needs_nominee_answer: "Waiting for nominee answer",
};

export const claimPathLabel = (p: string) => CLAIM_PATH_LABEL[p as ClaimPath] ?? p.replace(/_/g, " ");

export function confidenceLabel(c: number): "High" | "Medium" | "Low" {
  if (c >= 0.8) return "High";
  if (c >= 0.5) return "Medium";
  return "Low";
}

export const claimPackFilename = (institution: string, assetId: string) =>
  `claimpack_${institution.replace(/\s+/g, "_")}_${assetId}.docx`;
