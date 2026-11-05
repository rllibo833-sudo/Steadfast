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

const BUSINESS_TERMS = /\b(opportunit(y|ies)|market|customer|buyer|users?|revenue|pricing|saas|business|leverage|ads?|campaign|iklan|kampanye|peluang|pasar|pengguna|pembeli|pemasukan|pendapatan|harga|bisnis|laba|untung|pelanggan|usaha)\b/i;
const EXECUTION_TERMS = /\b(build|deploy|create|implement|publish|send|delete|update|change|write|buat|bangun|deploy|kirim|hapus|ubah|tulis|perbaiki)\b/i;

export function shouldRunBusinessTeam(task: string): boolean {
  return BUSINESS_TERMS.test(task) && !EXECUTION_TERMS.test(task);
}

export function extractScoutEvidence(result: { steps?: Array<{ toolResults?: Array<{ toolName?: string; output?: unknown; result?: unknown }> }> }): string[] {
  return (result.steps ?? []).flatMap((step) => step.toolResults ?? [])
    .map((item) => {
      const value = item.output ?? item.result ?? null;
      const serialized = JSON.stringify({ tool: item.toolName ?? "read-only", result: value });
      return { serialized, value };
    })
    .filter(({ serialized, value }) => {
      if (value === null || serialized.length <= 2) return false;
      if (/"(isError|error|errors)"\s*:\s*(true|\[|\{)/i.test(serialized)) return false;
      // A successful tool response without a concrete public source URL is not
      // evidence. Empty search results must stop the scout.
      return /https?:\/\//i.test(serialized);
    })
    .map(({ serialized }) => serialized);
}

export function containsUnsupportedUrls(answer: string, evidence: string[]): boolean {
  const allowed = new Set(evidence.flatMap((item) => item.match(/https?:\/\/[^\s"'<>]+/g) ?? []).map((url) => url.replace(/[),.;]+$/, "")));
  const cited = answer.match(/https?:\/\/[^\s"'<>]+/g) ?? [];
  return cited.some((url) => !allowed.has(url.replace(/[),.;]+$/, "")));
}

export function lacksEvidenceCitations(answer: string, evidence: string[]): boolean {
  const supportedUrls = evidence.flatMap((item) => item.match(/https?:\/\/[^\s"'<>]+/g) ?? []);
  const citedUrls = answer.match(/https?:\/\/[^\s"'<>]+/g) ?? [];
  return supportedUrls.length > 0 && citedUrls.length === 0;
}
