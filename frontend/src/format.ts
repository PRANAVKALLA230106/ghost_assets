/** ₹14,60,000 (Indian digit grouping). */
export const formatINR = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;

/** ₹14.6 lakh / ₹1.2 crore. */
export function formatLakh(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)} crore`;
  return `₹${(n / 1e5).toFixed(1)} lakh`;
}

/** Compact value for graph labels: ₹14.6L, ₹45K. */
export function formatShort(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
  if (n >= 1e3) return `₹${Math.round(n / 1e3)}K`;
  return `₹${Math.round(n)}`;
}
