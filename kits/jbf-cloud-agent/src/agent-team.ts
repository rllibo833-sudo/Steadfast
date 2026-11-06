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

export type OperationsRole = {
  id: string;
  name: string;
  purpose: string;
  preferredProvider: "openrouter-free" | "groq-free";
  match: RegExp;
  connectors: string[] | "all";
};

/** Specialist roles selected by the coordinator; they share one free inference call per task. */
export const OPERATIONS_AGENT_ROLES: OperationsRole[] = [
  { id: "database-manager", name: "Database Manager", purpose: "Mengelola database yang terhubung seperti Cloudflare D1/KV/R2 dan DigitalOcean; Supabase hanya untuk transport Steadfast menuju Mnemos-RLI cabang Knowledge, bukan database umum.", preferredProvider: "groq-free", match: /\b(database|db|sql|postgres|supabase|d1|kv|r2|basis data|tabel)\b/i, connectors: ["cloudflare", "digitalocean"] },
  { id: "seo-editor", name: "SEO & Content Editor", purpose: "Mengaudit SEO teknis dan menyusun atau memperbarui konten yang membantu pengguna, berdasarkan produk dan situs yang benar-benar terhubung.", preferredProvider: "openrouter-free", match: /\b(seo|search console|sitemap|robots|keyword|kata kunci|konten|artikel|blog|ranking|indeks)\b/i, connectors: ["github", "cloudflare"] },
  { id: "vps-operator", name: "VPS & Hosting Operator", purpose: "Menginventarisasi hosting/VPS, menjaga layanan, dan memilih opsi gratis terlebih dahulu; minta approval untuk resource berbiaya atau publikasi.", preferredProvider: "groq-free", match: /\b(vps|droplet|server|hosting|deploy|deployment|cloudflare|digitalocean|worker|workers|pages)\b/i, connectors: ["digitalocean", "cloudflare", "github"] },
  { id: "account-onboarding", name: "Account & Service Manager", purpose: "Mengelola akun dan layanan yang telah terhubung, menghubungkan provider melalui OAuth resmi, serta melaporkan langkah login/verifikasi yang perlu dilakukan pemilik tanpa mengaku tindakan selesai tanpa bukti.", preferredProvider: "openrouter-free", match: /\b(akun|account|daftar|registr|signup|sign up|buat akun|hubungkan akun|connect account|onboarding|credential|billing)\b/i, connectors: "all" },
  { id: "ads-manager", name: "Ads & Analytics Manager", purpose: "Membaca performa iklan dan analitik yang terhubung, menyiapkan optimasi, serta menahan perubahan budget atau delivery untuk approval spesifik.", preferredProvider: "groq-free", match: /\b(ads?|iklan|campaign|kampanye|meta ads|google ads|analytics|konversi)\b/i, connectors: ["meta-ads", "cloudflare", "github"] },
  { id: "product-algorithm", name: "Product & Algorithm Agent", purpose: "Menganalisis dan memperbaiki algoritma produk lewat repositori dan layanan yang terhubung; minta approval sebelum perubahan live.", preferredProvider: "openrouter-free", match: /\b(algoritma|algorithm|ranking|rekomendasi|recommendation|fitur|produk|product|bug|perbaiki|ubah kode)\b/i, connectors: ["github", "cloudflare"] },
];

export function selectOperationsRoles(task: string): OperationsRole[] {
  const selected = OPERATIONS_AGENT_ROLES.filter((role) => role.match.test(task));
  return selected.length ? selected : [];
}

const BUSINESS_TERMS = /\b(opportunit(y|ies)|market|customer|buyer|users?|revenue|pricing|saas|business|leverage|ads?|campaign|iklan|kampanye|peluang|pasar|pengguna|pembeli|pemasukan|pendapatan|harga|bisnis|laba|untung|pelanggan|usaha)\b/i;
const EXECUTION_TERMS = /\b(build|deploy|create|implement|publish|send|delete|update|change|write|register|registration|signup|sign up|onboard|connect|buat|bangun|deploy|kirim|hapus|ubah|tulis|perbaiki|daftar|registrasi|hubungkan)\b/i;

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
