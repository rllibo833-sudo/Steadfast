export type AgentRole = {
  id: string;
  name: string;
  purpose: string;
  preferredProvider: "openrouter-free" | "groq-free";
};

export const BUSINESS_AGENT_ROLES: AgentRole[] = [
  {
    id: "market-scout",
    name: "Market Scout",
    purpose: "Mencari bukti permintaan publik dan calon pengguna dari tool baca-saja yang terhubung.",
    preferredProvider: "openrouter-free",
  },
  {
    id: "unit-economics",
    name: "Unit Economics Analyst",
    purpose: "Menghitung biaya langsung, harga, kontribusi, leverage, dan titik impas dari bukti yang ditemukan.",
    preferredProvider: "groq-free",
  },
  {
    id: "risk-reviewer",
    name: "Evidence Reviewer",
    purpose: "Memeriksa sumber, asumsi, privasi, kuota, serta langkah yang membutuhkan persetujuan.",
    preferredProvider: "openrouter-free",
  },
];

const BUSINESS_TERMS = /\b(opportunit(y|ies)|market|customer|buyer|users?|revenue|pricing|saas|business|leverage|peluang|pasar|pengguna|pembeli|pemasukan|pendapatan|harga|bisnis|laba|untung|pelanggan|usaha)\b/i;
const EXECUTION_TERMS = /\b(build|deploy|create|implement|publish|send|delete|update|change|write|buat|bangun|deploy|kirim|hapus|ubah|tulis|perbaiki)\b/i;

export function shouldRunBusinessTeam(task: string): boolean {
  return BUSINESS_TERMS.test(task) && !EXECUTION_TERMS.test(task);
}

export function extractScoutEvidence(result: { steps?: Array<{ toolResults?: Array<{ toolName?: string; output?: unknown; result?: unknown }> }> }): string[] {
  return (result.steps ?? []).flatMap((step) => step.toolResults ?? [])
    .map((item) => JSON.stringify({ tool: item.toolName ?? "read-only", result: item.output ?? item.result ?? null }))
    .filter((item) => item.length > 2);
}

export function containsUnsupportedUrls(answer: string, evidence: string[]): boolean {
  const allowed = new Set(evidence.flatMap((item) => item.match(/https?:\/\/[^\s"'<>]+/g) ?? []).map((url) => url.replace(/[),.;]+$/, "")));
  const cited = answer.match(/https?:\/\/[^\s"'<>]+/g) ?? [];
  return cited.some((url) => !allowed.has(url.replace(/[),.;]+$/, "")));
}
