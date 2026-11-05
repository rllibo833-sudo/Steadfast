import { Agent, routeAgentRequest } from "agents";
import { createAI } from "agents/models/ai-sdk";
import { createOpenRouter } from "@openrouter/ai-sdk-provider";
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { generateText, stepCountIs } from "ai";
import { runFreeFirst, runFreeProviders } from "./provider-routing";
import { BUSINESS_AGENT_ROLES, containsUnsupportedUrls, extractScoutEvidence, lacksEvidenceCitations, shouldRunBusinessTeam } from "./agent-team";

interface Env {
  AI: Ai;
  JBF_AGENT: DurableObjectNamespace<JbfAgent>;
  ASSETS: Fetcher;
  OWNER_TOKEN: string;
  GITHUB_TOKEN: string;
  CLOUDFLARE_API_TOKEN: string;
  OPENROUTER_API_KEY?: string;
  GROQ_API_KEY?: string;
  GEMINI_API_KEY?: string;
  GEMINI_FREE_DATA_APPROVED?: string;
  CEREBRAS_API_KEY?: string;
  NVIDIA_API_KEY?: string;
  BUSINESS_EMAIL: string;
  BUSINESS_WHATSAPP: string;
}

type Connector = { id: string; label: string; url: string };
type Approval = Record<string, unknown> & { id: string; taskId: string; status: string };
type ProviderInfo = { id: string; category: string; auth: string; availability: string; note: string; connector?: string };
const CONNECTORS: Record<string, Connector> = {
  github: { id: "github", label: "GitHub", url: "https://api.githubcopilot.com/mcp/" },
  cloudflare: { id: "cloudflare", label: "Cloudflare", url: "https://mcp.cloudflare.com/mcp" },
  supabase: { id: "supabase", label: "Supabase (read-only default)", url: "https://mcp.supabase.com/mcp?read_only=true" },
  digitalocean: { id: "digitalocean", label: "DigitalOcean (VPS, apps, databases)", url: "https://mcp.digitalocean.com/mcp" },
  "meta-ads": { id: "meta-ads", label: "Meta Ads (Facebook and Instagram)", url: "https://mcp.facebook.com/ads" },
};
const PROVIDERS: ProviderInfo[] = [
  { id: "github", category: "repositori, CI, kode", auth: "Kredensial GitHub yang sudah terpasang", availability: "ready", note: "Gunakan akun/repo yang ada; perubahan menunggu approval.", connector: "github" },
  { id: "cloudflare", category: "hosting, D1/KV/R2, AI", auth: "Token Cloudflare yang sudah terpasang", availability: "ready", note: "Prioritaskan Workers/Pages, D1/KV/R2, dan AI gratis; jangan aktifkan billing.", connector: "cloudflare" },
  { id: "github-actions", category: "compute sementara", auth: "Kredensial GitHub yang sudah terpasang", availability: "ready", note: "Runner bisa menjalankan job sementara; jangan sebut VPS persisten.", connector: "github" },
  { id: "supabase", category: "database, storage, functions", auth: "OAuth dinamis, persetujuan browser", availability: "connected_read_only", note: "Koneksi saat ini read-only. Jangan mengaku bisa menulis; pilih Cloudflare D1 atau berhenti jika tugas perlu mutasi Supabase.", connector: "supabase" },
  { id: "digitalocean", category: "VPS, App Platform, database, networking", auth: "DigitalOcean OAuth melalui browser", availability: "approval_required_on_connect", note: "Dapat mengelola Droplet, apps, dan database setelah koneksi. Resource dapat menimbulkan biaya; tampilkan biaya dan minta approval sebelum setiap perubahan billable.", connector: "digitalocean" },
  { id: "meta-ads", category: "iklan, kampanye, insight dan optimasi", auth: "Meta OAuth dan akses ad account; fitur dapat bergantung pada rollout akun", availability: "approval_required_on_connect", note: "Gunakan untuk membaca performa dan menyusun optimasi. Perubahan iklan, targeting, budget, atau delivery wajib menunggu approval spesifik; jangan mengaktifkan belanja otomatis.", connector: "meta-ads" },
  { id: "gmail", category: "email", auth: "Google Cloud project, Gmail API, OAuth client", availability: "manual_setup_required", note: "Lewati; jangan meminta owner membuat project atau memasukkan API." },
  { id: "whatsapp", category: "pesan", auth: "Meta app, WhatsApp Business, phone ID, token", availability: "manual_setup_required", note: "Lewati sampai tersedia onboarding resmi tanpa pengisian kredensial manual." },
  { id: "vps", category: "virtual server", auth: "Belum ada provider VPS terhubung", availability: "discover_only", note: "Cari opsi gratis tanpa kartu/identitas manual; jangan mulai trial berbayar." },
  { id: "github-models", category: "AI inference", auth: "Tidak tersedia", availability: "retired", note: "Sudah dihentikan; jangan dipakai sebagai fallback." },
  { id: "openrouter-free", category: "AI inference gratis cadangan 1", auth: "Kredensial OpenRouter yang sudah tersimpan", availability: "not_configured", note: "Hanya openrouter/free; tidak membeli kredit dan tidak menggunakan model berbayar." },
  { id: "groq-free", category: "AI inference gratis cadangan 2", auth: "Kredensial Groq tersimpan sebagai Worker secret", availability: "not_configured", note: "Groq free tier; batas gratis berlaku." },
  { id: "cerebras-free", category: "AI inference gratis cadangan 3", auth: "API key Cerebras sebagai Worker secret", availability: "not_configured", note: "Cerebras Free tier (rate limit berlaku); kandidat model GLM 4.7." },
  { id: "nvidia-nim-free", category: "AI inference gratis cadangan 4", auth: "API key NVIDIA NIM sebagai Worker secret", availability: "not_configured", note: "Pakai hanya model yang saat ini berlabel Free Endpoint; ketersediaan dan rate limit dapat berubah." },
  { id: "gemini-free", category: "AI inference gratis cadangan 5", auth: "API key Gemini sebagai Worker secret + persetujuan penggunaan data free tier", availability: "not_configured", note: "Free tier terbatas. Google menyatakan konten free tier dapat dipakai untuk peningkatan produk; hanya aktif bila owner menyetujui penggunaan untuk prompt non-rahasia." },
];
const SYSTEM = `You are JBF, the owner's self-operating infrastructure, growth, and SaaS agent. The owner's priority is real users and revenue before spending. Manage connected hosting, VPS, databases, SaaS, ads, analytics, and product algorithms through the provider catalog; inspect actual connection state and capability before proposing or acting. For DigitalOcean, inspect account resources first; do not create or resize billable resources without exact owner approval. For ad accounts, analyze performance and propose experiments from measured data; never launch, increase budget, change audience/bids, or enable delivery without approval showing platform, campaign, exact change, and maximum daily/lifetime spend. Treat algorithm changes to a live product with the same approval gate. Compare opportunities using verifiable buyer evidence, route to the first real user and first payment, time to launch, direct cash cost, recurring cost, gross margin, and break-even users. Prefer an existing/free path and a small experiment that can validate demand. Separate observed evidence from estimates, show the arithmetic and uncertainty, and never present a lead, signup, deployment, or revenue as completed without tool evidence. For the owner's example, Rp1,000,000 revenue against Rp200,000 direct spend means 5x revenue-to-spend and Rp800,000 contribution before labor, tax, and other costs; it is a target calculation, not a forecast or guarantee. Before any paid plan, billable resource, purchase, account creation, acceptance of terms, public release, deployment, or outbound message, present the exact action and its one-time and recurring cost and wait for the owner's approval. Never enter payment details or use personal identity/contact information for registration unless the exact account and fields are approved. Use existing credentials and supported OAuth flows where possible; if a provider requires manual identity verification or unsupported registration, give its official link and state the blocker without claiming signup. Use connected read-only tools for public prospect discovery; cite exact URLs and evidence, and do not spam unrelated projects. For game art leads, prioritize public requests for artists, collaborators, asset feedback, or paid commissions. Keep Supabase read-only and project-scoped by default; do not claim write access. Treat GitHub Actions as temporary compute, not a persistent VPS. For VPS options, compare official free tiers, limits, region, storage, sleep behavior, and card/identity requirements before recommending one. Do not assume Steadfast is the product: compare game-studio tools, image/video generation, and other SaaS services by buyer evidence and fastest low-cost route to income. When asked to build, implement with connected GitHub and hosting tools, then queue deploy or other external writes for exact owner approval and continue the task afterward. For business/opportunity research without an execution request, use the Market Scout, Unit Economics Analyst, and Evidence Reviewer in sequence. They share only configured free model providers and the Scout receives read-only tools. Do not invent market signals, product pricing, free quotas, or provider capabilities. If there are no verifiable sources with concrete URLs, say no evidence was found and stop recommendations. Use free inference first: Cloudflare Workers AI, OpenRouter openrouter/free, Groq Free, Cerebras Free, and NVIDIA NIM endpoints currently marked Free. Gemini Free is available only when the owner explicitly approves its data-use terms; never send secrets or confidential data there. Stop if configured free options fail; never switch to paid inference without approval. Never activate paid inference, billing, or a paid fallback without explicit approval. Prepare tailored outreach drafts, but do not send without approval. Keep replies concise and in the user's language.`;

function json(data: unknown, status = 200): Response {
  return Response.json(data, { status, headers: { "cache-control": "no-store" } });
}
function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [
    key,
    /token|secret|password|api.?key|authorization|credential|private.?key/i.test(key) ? "[REDACTED]" : redact(item),
  ]));
}

export class JbfAgent extends Agent<Env> {
  private async runTask(taskId: string, instruction: string): Promise<{ text: string; provider: string }> {
    await this.mcp.waitForConnections({ timeout: 8_000 });
    const tools = this.mcp.getAITools();
    const catalog = this.mcp.listTools();
    if (catalog.length === 0) throw new Error("Connected services exposed no remote tools. Reconnect GitHub and Cloudflare before asking the agent to manage them.");
    const servers = this.getMcpServers().servers;
    const providerContext = PROVIDERS.map((provider) => ({
      id: provider.id,
      category: provider.category,
      auth: provider.auth,
      availability: provider.connector
        ? (servers[provider.connector]?.state ?? "disconnected")
        : provider.id === "openrouter-free" && this.env.OPENROUTER_API_KEY
          ? "ready_fallback"
          : provider.id === "groq-free" && this.env.GROQ_API_KEY
            ? "ready_fallback"
            : provider.id === "cerebras-free" && this.env.CEREBRAS_API_KEY
              ? "ready_fallback"
              : provider.id === "nvidia-nim-free" && this.env.NVIDIA_API_KEY
                ? "ready_fallback"
              : provider.id === "gemini-free" && this.env.GEMINI_API_KEY && this.env.GEMINI_FREE_DATA_APPROVED === "true"
                ? "ready_fallback"
        : provider.availability,
      note: provider.note,
    }));
    for (const [key, tool] of Object.entries(tools)) {
      if (!tool.execute) continue;
      const execute = tool.execute;
      const raw = catalog.find((item) => key === `tool_${item.serverId}_${item.name}`);
      const isReadOnly = raw?.annotations?.readOnlyHint === true
        || (raw?.serverId === "cloudflare" && ["docs", "search", "whoami"].includes(raw.name));
      tool.execute = async (input: unknown) => {
        if (isReadOnly) return execute(input as never);
        const id = crypto.randomUUID();
        const approvals = await this.ctx.storage.get<Approval[]>("approvals") ?? [];
        if (approvals.filter((item) => item.status === "pending").length >= 100) {
          return { status: "approval_queue_full", summary: "Approval queue is full. Wait for owner review." };
        }
        approvals.push({ id, taskId, toolKey: key, input, status: "pending", createdAt: new Date().toISOString() });
        await this.ctx.storage.put("approvals", approvals);
        return { status: "awaiting_owner_approval", approvalId: id, summary: `Queued ${key} for one-call owner approval. Do not claim it completed.` };
      };
    }
    const readOnlyKeys = new Set(catalog.filter((item) =>
      item.annotations?.readOnlyHint === true
      || (item.serverId === "cloudflare" && ["docs", "search", "whoami"].includes(item.name)),
    ).map((item) => `tool_${item.serverId}_${item.name}`));
    const readOnlyTools = Object.fromEntries(Object.entries(tools).filter(([key]) => readOnlyKeys.has(key))) as typeof tools;
    const ai = createAI({ binding: this.env.AI });
    const generation = {
      system: `${SYSTEM}\n\nAdditional inference policy: use configured free providers in this order after Cloudflare: OpenRouter Free, Groq Free, Cerebras Free, NVIDIA NIM free endpoints, then Gemini Free only when GEMINI_FREE_DATA_APPROVED is true. Cerebras Free and NVIDIA NIM Free Endpoints have rate limits. Gemini Free inputs may be used by Google to improve products; never route secrets, personal data, or confidential business data there. Never use paid inference.\n\nProvider catalog: ${JSON.stringify(providerContext)}\n\nOwner business contact (for approved outreach drafts only): email=${this.env.BUSINESS_EMAIL || "unavailable"}; WhatsApp=${this.env.BUSINESS_WHATSAPP || "unavailable"}.`,
      prompt: instruction,
      tools,
      stopWhen: stepCountIs(8),
    };
    const openrouter = this.env.OPENROUTER_API_KEY
      ? createOpenRouter({ apiKey: this.env.OPENROUTER_API_KEY })
      : undefined;
    const groq = this.env.GROQ_API_KEY
      ? createOpenAICompatible({
          name: "groq",
          baseURL: "https://api.groq.com/openai/v1",
          apiKey: this.env.GROQ_API_KEY,
        })
      : undefined;
    const cerebras = this.env.CEREBRAS_API_KEY
      ? createOpenAICompatible({ name: "cerebras", baseURL: "https://api.cerebras.ai/v1", apiKey: this.env.CEREBRAS_API_KEY })
      : undefined;
    const nvidia = this.env.NVIDIA_API_KEY
      ? createOpenAICompatible({ name: "nvidia-nim", baseURL: "https://integrate.api.nvidia.com/v1", apiKey: this.env.NVIDIA_API_KEY })
      : undefined;
    const gemini = this.env.GEMINI_API_KEY && this.env.GEMINI_FREE_DATA_APPROVED === "true"
      ? createOpenAICompatible({ name: "gemini", baseURL: "https://generativelanguage.googleapis.com/v1beta/openai/", apiKey: this.env.GEMINI_API_KEY })
      : undefined;
    if (shouldRunBusinessTeam(instruction)) {
      const publicProviders = JSON.stringify(providerContext.map(({ id, availability, category }) => ({ id, availability, category })));
      const runRole = async (roleId: "market-scout" | "unit-economics" | "risk-reviewer", prompt: string, roleTools: typeof tools) => {
        const role = BUSINESS_AGENT_ROLES.find((item) => item.id === roleId)!;
        const roleSystem = `${SYSTEM}\n\nYou are the ${role.name} (${role.id}). ${role.purpose} Use only the evidence and tools provided. Never invent a source, buyer, price, quota, or completed action.\n\nConnected provider status: ${publicProviders}`;
        const generation = {
          system: roleSystem,
          prompt,
          tools: roleTools,
          stopWhen: stepCountIs(roleId === "market-scout" ? 4 : 1),
        };
        const openRouterRun = () => generateText({ ...generation, model: openrouter!("openrouter/free") });
        const groqRun = () => generateText({ ...generation, model: groq!.chatModel("openai/gpt-oss-120b") });
        const cerebrasRun = () => generateText({ ...generation, model: cerebras!.chatModel("zai-glm-4.7") });
        const nvidiaRun = () => generateText({ ...generation, model: nvidia!.chatModel("nvidia/nemotron-3.5-lightning-30b-a3b") });
        const geminiRun = () => generateText({ ...generation, model: gemini!.chatModel("gemini-3.8-flash") });
        const candidates = role.preferredProvider === "openrouter-free"
          ? [
              { id: "openrouter-free", available: Boolean(openrouter), run: openRouterRun },
              { id: "groq-free", available: Boolean(groq), run: groqRun },
              { id: "cerebras-free", available: Boolean(cerebras), run: cerebrasRun },
              { id: "nvidia-nim-free", available: Boolean(nvidia), run: nvidiaRun },
              ...(role.id === "market-scout" ? [] : [{ id: "gemini-free", available: Boolean(gemini), run: geminiRun }]),
            ]
          : [
              { id: "groq-free", available: Boolean(groq), run: groqRun },
              { id: "openrouter-free", available: Boolean(openrouter), run: openRouterRun },
              { id: "cerebras-free", available: Boolean(cerebras), run: cerebrasRun },
              { id: "nvidia-nim-free", available: Boolean(nvidia), run: nvidiaRun },
              ...(role.id === "market-scout" ? [] : [{ id: "gemini-free", available: Boolean(gemini), run: geminiRun }]),
            ];
        return runFreeProviders(candidates);
      };
      const scout = await runRole(
        "market-scout",
        `Research this opportunity using only read-only tools. Find up to five public signals of demand and include exact source URLs. If no relevant read-only source is available, say so plainly.\n\nOwner request: ${instruction}`,
        readOnlyTools,
      );
      const scoutEvidence = extractScoutEvidence(scout.value);
      if (scoutEvidence.length === 0) {
        return {
          text: "Saya belum menemukan bukti permintaan yang dapat diverifikasi dari sumber baca-saja yang terhubung. Belum ada rekomendasi pasar atau klaim pengguna/pemasukan. Hubungkan sumber publik yang relevan atau berikan niche untuk riset berikutnya.",
          provider: `business-team: market-scout=${scout.provider}; evidence=none`,
        };
      }
      const evidenceBundle = scoutEvidence.join("\n").slice(0, 24_000);
      const economics = await runRole(
        "unit-economics",
        `Assess the economics using only the raw read-only tool results below. Do not infer demand from repository existence or activity. Show formulas only; mark every unverified price or volume as a hypothetical assumption.\n\nOwner request: ${instruction}\n\nRaw tool results: ${evidenceBundle}`,
        {},
      );
      const review = await runRole(
        "risk-reviewer",
        `Review the raw tool evidence and calculations below. Only state buyer-demand claims directly supported by the raw results. Existing repos, stars, or issues alone are not proof of purchase intent. Do not introduce any URL absent from the raw results. If evidence is weak, say no verified demand signal was found. Mark all prices as unknown unless directly sourced. Reply in the owner's language.\n\nOwner request: ${instruction}\n\nRaw read-only tool results: ${evidenceBundle}\n\nUnit Economics: ${economics.value.text}`,
        {},
      );
      return {
        text: containsUnsupportedUrls(review.value.text, scoutEvidence) || lacksEvidenceCitations(review.value.text, scoutEvidence)
          ? "Riset belum memenuhi standar bukti: sumber tidak bisa dicocokkan atau jawaban tidak menyertakan tautan sumber. Saya menahan rekomendasi dan klaim pasar/biaya."
          : review.value.text,
        provider: `business-team: market-scout=${scout.provider}, unit-economics=${economics.provider}, reviewer=${review.provider}`,
      };
    }

    const result = await runFreeFirst(
      () => generateText({ ...generation, model: ai("@cf/zai-org/glm-4.7-flash") }),
      [
        {
          id: "openrouter-free",
          available: Boolean(openrouter),
          run: () => generateText({ ...generation, model: openrouter!("openrouter/free") }),
        },
        {
          id: "groq-free",
          available: Boolean(groq),
          run: () => generateText({ ...generation, model: groq!.chatModel("openai/gpt-oss-120b") }),
        },
        {
          id: "cerebras-free",
          available: Boolean(cerebras),
          run: () => generateText({ ...generation, model: cerebras!.chatModel("zai-glm-4.7") }),
        },
        {
          id: "nvidia-nim-free",
          available: Boolean(nvidia),
          run: () => generateText({ ...generation, model: nvidia!.chatModel("nvidia/nemotron-3.5-lightning-30b-a3b") }),
        },
        {
          id: "gemini-free",
          available: Boolean(gemini),
          run: () => generateText({ ...generation, model: gemini!.chatModel("gemini-3.8-flash") }),
        },
      ],
    );
    return { text: result.value.text, provider: result.provider };
  }

  async onRequest(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const route = url.pathname.split("/").filter(Boolean).at(-1) ?? "";

    if (route === "connect" && request.method === "POST") {
      const body = await request.json().then((value) => value as { provider?: string }).catch(() => ({} as { provider?: string }));
      const connector = body.provider ? CONNECTORS[body.provider] : undefined;
      if (!connector) return json({ error: "Connector not supported" }, 400);
      const existing = this.getMcpServers().servers[connector.id];
      if (existing && existing.server_url !== connector.url) {
        await this.removeMcpServer(connector.id);
      }
      const headers: Record<string, string> = {};
      if (connector.id === "github") headers.Authorization = `Bearer ${this.env.GITHUB_TOKEN}`;
      if (connector.id === "cloudflare") headers.Authorization = `Bearer ${this.env.CLOUDFLARE_API_TOKEN}`;
      const result = await this.addMcpServer(connector.label, connector.url, {
        id: connector.id,
        ...(Object.keys(headers).length ? { transport: { type: "streamable-http" as const, headers } } : {}),
      });
      if (result.state === "authenticating") return json({ state: result.state, authUrl: result.authUrl });
      return json({ state: result.state, id: result.id });
    }

    if (route === "agents" && request.method === "GET") {
      const enabled = Boolean(this.env.OPENROUTER_API_KEY || this.env.GROQ_API_KEY || this.env.CEREBRAS_API_KEY || this.env.NVIDIA_API_KEY || (this.env.GEMINI_API_KEY && this.env.GEMINI_FREE_DATA_APPROVED === "true"));
      return json({
        agents: BUSINESS_AGENT_ROLES.map((agent) => ({ ...agent, enabled, execution: "read-only research roles; no extra roles run for ordinary tasks" })),
        providerAgents: PROVIDERS.filter((provider) => provider.category.startsWith("AI inference")).map((provider) => ({
          id: provider.id,
          name: provider.id,
          purpose: provider.note,
          enabled: provider.id === "openrouter-free" ? Boolean(this.env.OPENROUTER_API_KEY)
            : provider.id === "groq-free" ? Boolean(this.env.GROQ_API_KEY)
            : provider.id === "cerebras-free" ? Boolean(this.env.CEREBRAS_API_KEY)
            : provider.id === "nvidia-nim-free" ? Boolean(this.env.NVIDIA_API_KEY)
            : provider.id === "gemini-free" ? Boolean(this.env.GEMINI_API_KEY && this.env.GEMINI_FREE_DATA_APPROVED === "true")
            : false,
        })),
      });
    }

    if (route === "providers" && request.method === "GET") {
      await this.mcp.waitForConnections({ timeout: 8_000 });
      const state = this.getMcpServers();
      return json({ providers: PROVIDERS.map((provider) => ({
        ...provider,
        state: provider.connector ? (state.servers[provider.connector]?.state ?? "disconnected")
          : provider.id === "openrouter-free" && this.env.OPENROUTER_API_KEY ? "ready_fallback"
          : provider.id === "groq-free" && this.env.GROQ_API_KEY ? "ready_fallback"
          : provider.id === "cerebras-free" && this.env.CEREBRAS_API_KEY ? "ready_fallback"
          : provider.id === "nvidia-nim-free" && this.env.NVIDIA_API_KEY ? "ready_fallback"
          : provider.id === "gemini-free" && this.env.GEMINI_API_KEY && this.env.GEMINI_FREE_DATA_APPROVED === "true" ? "ready_fallback" : provider.availability,
        connected: provider.connector ? state.servers[provider.connector]?.state === "ready"
          : (provider.id === "openrouter-free" && Boolean(this.env.OPENROUTER_API_KEY))
            || (provider.id === "cerebras-free" && Boolean(this.env.CEREBRAS_API_KEY))
            || (provider.id === "nvidia-nim-free" && Boolean(this.env.NVIDIA_API_KEY))
            || (provider.id === "groq-free" && Boolean(this.env.GROQ_API_KEY))
            || (provider.id === "gemini-free" && Boolean(this.env.GEMINI_API_KEY && this.env.GEMINI_FREE_DATA_APPROVED === "true")),
      })) });
    }

    if (route === "status" && request.method === "GET") {
      await this.mcp.waitForConnections({ timeout: 8_000 });
      const state = this.getMcpServers();
      return json({
        connectors: Object.values(CONNECTORS).map((c) => ({
          id: c.id,
          label: c.label,
          connected: state.servers[c.id]?.state === "ready",
          state: state.servers[c.id]?.state ?? "disconnected",
          error: state.servers[c.id]?.error ?? undefined,
        })),
        tools: state.tools.map((tool) => ({
          serverId: tool.serverId, name: tool.name,
          title: tool.title ?? tool.annotations?.title ?? tool.name,
          readOnly: tool.annotations?.readOnlyHint === true,
        })),
        approvals: redact(await this.ctx.storage.get<Approval[]>("approvals") ?? []),
      });
    }

    if (route === "chat" && request.method === "POST") {
      const body = await request.json().then((value) => value as { message?: string }).catch(() => ({} as { message?: string }));
      const message = typeof body.message === "string" ? body.message.slice(0, 8000) : "";
      if (!message.trim()) return json({ error: "Message is required" }, 400);
      const taskId = crypto.randomUUID();
      await this.ctx.storage.put(`task:${taskId}`, { prompt: message, progress: [] });
      try {
        const completion = await this.runTask(taskId, message);
        return json({ taskId, ...completion });
      } catch (error) {
        const detail = String(error);
        if (/429|3036|3040|quota|limit|billing|exceeded|allocation|neurons|resource.?exhausted|rate.?limit/i.test(detail)) {
          return json({ error: "Configured free inference providers (Cloudflare, OpenRouter, Groq, Cerebras, NVIDIA, Gemini opt-in) are unavailable. The agent stopped; no paid fallback is configured." }, 429);
        }
        return json({ error: "Agent request failed", detail: detail.slice(0, 500) }, 502);
      }
    }

    if (route === "complete" && request.method === "POST") {
      const body = await request.json().then((value) => value as { taskId?: string }).catch(() => ({} as { taskId?: string }));
      if (!body.taskId) return json({ error: "Task id required" }, 400);
      const approvals = await this.ctx.storage.get<Approval[]>("approvals") ?? [];
      if (approvals.some((item) => item.taskId === body.taskId && item.status === "pending")) {
        return json({ error: "Task still has pending approvals" }, 409);
      }
      await this.ctx.storage.delete(`task:${body.taskId}`);
      return json({ status: "completed" });
    }

    if (route === "approve" && request.method === "POST") {
      const body = await request.json().then((value) => value as { id?: string; decision?: string }).catch(() => ({} as { id?: string; decision?: string }));
      if (!body.id || !["approve", "deny"].includes(body.decision ?? "")) return json({ error: "Provide approval id and approve/deny decision" }, 400);
      const approvals = await this.ctx.storage.get<Approval[]>("approvals") ?? [];
      const index = approvals.findIndex((item) => item.id === body.id && item.status === "pending");
      if (index < 0) return json({ error: "Approval not found or already handled" }, 404);
      const action = approvals[index];
      let result: unknown = { status: "denied" };
      if (body.decision === "approve") {
        await this.mcp.waitForConnections({ timeout: 8_000 });
        const tool = this.mcp.getAITools()[String(action.toolKey)];
        if (!tool?.execute) return json({ error: "Connector tool is unavailable; reconnect it and review this request again" }, 409);
        try {
          result = await tool.execute(action.input as never);
        } catch (error) {
          result = { error: String(error).slice(0, 500) };
        }
      }
      approvals[index] = { ...action, status: body.decision === "approve" ? "approved_and_executed" : "denied", decidedAt: new Date().toISOString(), result: redact(result) };
      await this.ctx.storage.put("approvals", approvals);

      const task = await this.ctx.storage.get<{ prompt: string; progress: unknown[] }>(`task:${action.taskId}`);
      let continuation = "";
      let continuationProvider = "";
      if (task) {
        const compact = (value: unknown) => JSON.stringify(redact(value)).slice(0, 1600);
        task.progress.push({ decision: body.decision, tool: action.toolKey, input: compact(action.input), result: compact(result) });
        task.progress = task.progress.slice(-2);
        await this.ctx.storage.put(`task:${action.taskId}`, task);
        const prior = JSON.stringify(task.progress).slice(0, 12000);
        try {
          const completion = await this.runTask(action.taskId,
            `Original task: ${task.prompt}\n\nCompleted/denied actions so far (do not repeat them): ${prior}\n\nContinue the original task autonomously. If another external action is needed, queue it for approval.`);
          continuation = completion.text;
          continuationProvider = completion.provider;
        } catch (error) {
          continuation = `Task continuation stopped: ${String(error).slice(0, 400)}`;
        }
      }
      return json({ status: body.decision === "approve" ? "executed" : "denied", result: redact(result), continuation, continuationProvider });
    }

    return json({ error: "Not found" }, 404);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const isOAuthCallback = /\/agents\/jbf-agent\/owner\/callback\/?$/.test(url.pathname);
    if (!isOAuthCallback) {
      const auth = request.headers.get("authorization");
      if (!env.OWNER_TOKEN || auth !== `Bearer ${env.OWNER_TOKEN}`) return json({ error: "Unauthorized" }, 401);
    }
    const agentResponse = await routeAgentRequest(request, env, { prefix: "agents" });
    if (agentResponse) return agentResponse;
    if (url.pathname.startsWith("/agents/")) return json({ error: "Agent route not found" }, 404);
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
