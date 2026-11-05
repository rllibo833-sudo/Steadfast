import { Agent, routeAgentRequest } from "agents";
import { createAI } from "agents/models/ai-sdk";
import { generateText, stepCountIs } from "ai";

interface Env {
  AI: Ai;
  JBF_AGENT: DurableObjectNamespace<JbfAgent>;
  ASSETS: Fetcher;
  OWNER_TOKEN: string;
  GITHUB_TOKEN: string;
  CLOUDFLARE_API_TOKEN: string;
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
};
const PROVIDERS: ProviderInfo[] = [
  { id: "github", category: "repositori, CI, kode", auth: "Kredensial GitHub yang sudah terpasang", availability: "ready", note: "Gunakan akun/repo yang ada; perubahan menunggu approval.", connector: "github" },
  { id: "cloudflare", category: "hosting, D1/KV/R2, AI", auth: "Token Cloudflare yang sudah terpasang", availability: "ready", note: "Prioritaskan Workers/Pages, D1/KV/R2, dan AI gratis; jangan aktifkan billing.", connector: "cloudflare" },
  { id: "github-actions", category: "compute sementara", auth: "Kredensial GitHub yang sudah terpasang", availability: "ready", note: "Runner bisa menjalankan job sementara; jangan sebut VPS persisten.", connector: "github" },
  { id: "supabase", category: "database, storage, functions", auth: "OAuth dinamis, persetujuan browser", availability: "connected_read_only", note: "Koneksi saat ini read-only. Jangan mengaku bisa menulis; pilih Cloudflare D1 atau berhenti jika tugas perlu mutasi Supabase.", connector: "supabase" },
  { id: "gmail", category: "email", auth: "Google Cloud project, Gmail API, OAuth client", availability: "manual_setup_required", note: "Lewati; jangan meminta owner membuat project atau memasukkan API." },
  { id: "whatsapp", category: "pesan", auth: "Meta app, WhatsApp Business, phone ID, token", availability: "manual_setup_required", note: "Lewati sampai tersedia onboarding resmi tanpa pengisian kredensial manual." },
  { id: "vps", category: "virtual server", auth: "Belum ada provider VPS terhubung", availability: "discover_only", note: "Cari opsi gratis tanpa kartu/identitas manual; jangan mulai trial berbayar." },
  { id: "github-models", category: "AI inference", auth: "Tidak tersedia", availability: "retired", note: "Sudah dihentikan; jangan dipakai sebagai fallback." },
];
const SYSTEM = "You are JBF, the owner's self-operating cloud agent. Discover providers from the provider catalog before acting. Prefer already connected services or OAuth dynamic registration that needs only one owner browser approval. Never ask the owner to sign up, create an OAuth app, paste API keys, enter card details, or perform routine setup. If a provider requires those steps, skip it and search for another free provider. Search official provider docs and connected GitHub/Cloudflare sources to verify current free hosting, database, VPS, and AI model options; do not guess. Keep Supabase read-only and project-scoped by default; never broaden access to every project. Do not assume Steadfast is the product: compare game-studio tools, image/video generation, and other SaaS services using buyer evidence and the fastest free path to income. When asked to build, implement with connected GitHub/Cloudflare tools and deploy after approval; do not return only a plan when tools can do the work. Use free services only; never activate billing or paid fallback. Prepare outreach drafts but never claim buyers or payments without evidence. Owner contact may only be used for approved outreach or approved public listings. Read-only tools explicitly marked readOnlyHint may run automatically. Queue every other external action for approval and continue the task after approval. If free model quota/capacity blocks work, report it and stop. Never use OpenAI, Codex, or paid fallbacks. Keep replies concise and in the user's language.";

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
  private async runTask(taskId: string, instruction: string): Promise<string> {
    await this.mcp.waitForConnections({ timeout: 8_000 });
    const tools = this.mcp.getAITools();
    const catalog = this.mcp.listTools();
    const servers = this.getMcpServers().servers;
    const providerContext = PROVIDERS.map((provider) => ({
      id: provider.id,
      category: provider.category,
      auth: provider.auth,
      availability: provider.connector
        ? (servers[provider.connector]?.state ?? "disconnected")
        : provider.availability,
      note: provider.note,
    }));
    for (const [key, tool] of Object.entries(tools)) {
      if (!tool.execute) continue;
      const execute = tool.execute;
      const raw = catalog.find((item) => key === `tool_${item.serverId}_${item.name}`);
      const isReadOnly = raw?.annotations?.readOnlyHint === true;
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
    const ai = createAI({ binding: this.env.AI });
    const result = await generateText({
      model: ai("@cf/zai-org/glm-4.7-flash"),
      system: `${SYSTEM}\n\nProvider catalog: ${JSON.stringify(providerContext)}\n\nOwner business contact (for approved outreach drafts only): email=${this.env.BUSINESS_EMAIL || "unavailable"}; WhatsApp=${this.env.BUSINESS_WHATSAPP || "unavailable"}.`,
      prompt: instruction,
      tools,
      stopWhen: stepCountIs(3),
    });
    return result.text;
  }

  async onRequest(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const route = url.pathname.split("/").filter(Boolean).at(-1) ?? "";

    if (route === "connect" && request.method === "POST") {
      const body = await request.json().then((value) => value as { provider?: string }).catch(() => ({}));
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

    if (route === "providers" && request.method === "GET") {
      const state = this.getMcpServers();
      return json({ providers: PROVIDERS.map((provider) => ({
        ...provider,
        state: provider.connector ? (state.servers[provider.connector]?.state ?? "disconnected") : provider.availability,
        connected: provider.connector ? state.servers[provider.connector]?.state === "ready" : false,
      })) });
    }

    if (route === "status" && request.method === "GET") {
      const state = this.getMcpServers();
      return json({
        connectors: Object.values(CONNECTORS).map((c) => ({
          id: c.id,
          label: c.label,
          connected: state.servers[c.id]?.state === "ready",
          state: state.servers[c.id]?.state ?? "disconnected",
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
      const body = await request.json().then((value) => value as { message?: string }).catch(() => ({}));
      const message = typeof body.message === "string" ? body.message.slice(0, 8000) : "";
      if (!message.trim()) return json({ error: "Message is required" }, 400);
      const taskId = crypto.randomUUID();
      await this.ctx.storage.put(`task:${taskId}`, { prompt: message, progress: [] });
      try {
        const text = await this.runTask(taskId, message);
        return json({ taskId, text });
      } catch (error) {
        const detail = String(error);
        if (/429|3036|3040|quota|limit|billing|exceeded/i.test(detail)) {
          return json({ error: "Free Cloudflare AI is temporarily unavailable (daily quota or capacity). The agent stopped; no paid fallback is configured." }, 429);
        }
        return json({ error: "Agent request failed", detail: detail.slice(0, 500) }, 502);
      }
    }

    if (route === "complete" && request.method === "POST") {
      const body = await request.json().then((value) => value as { taskId?: string }).catch(() => ({}));
      if (!body.taskId) return json({ error: "Task id required" }, 400);
      const approvals = await this.ctx.storage.get<Approval[]>("approvals") ?? [];
      if (approvals.some((item) => item.taskId === body.taskId && item.status === "pending")) {
        return json({ error: "Task still has pending approvals" }, 409);
      }
      await this.ctx.storage.delete(`task:${body.taskId}`);
      return json({ status: "completed" });
    }

    if (route === "approve" && request.method === "POST") {
      const body = await request.json().then((value) => value as { id?: string; decision?: string }).catch(() => ({}));
      if (!body.id || !["approve", "deny"].includes(body.decision ?? "")) return json({ error: "Provide approval id and approve/deny decision" }, 400);
      const approvals = await this.ctx.storage.get<Approval[]>("approvals") ?? [];
      const index = approvals.findIndex((item) => item.id === body.id && item.status === "pending");
      if (index < 0) return json({ error: "Approval not found or already handled" }, 404);
      const action = approvals[index];
      let result: unknown = { status: "denied" };
      if (body.decision === "approve") {
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
      if (task) {
        const compact = (value: unknown) => JSON.stringify(redact(value)).slice(0, 1600);
        task.progress.push({ decision: body.decision, tool: action.toolKey, input: compact(action.input), result: compact(result) });
        task.progress = task.progress.slice(-2);
        await this.ctx.storage.put(`task:${action.taskId}`, task);
        const prior = JSON.stringify(task.progress).slice(0, 12000);
        try {
          continuation = await this.runTask(action.taskId,
            `Original task: ${task.prompt}\n\nCompleted/denied actions so far (do not repeat them): ${prior}\n\nContinue the original task autonomously. If another external action is needed, queue it for approval.`);
        } catch (error) {
          continuation = `Task continuation stopped: ${String(error).slice(0, 400)}`;
        }
      }
      return json({ status: body.decision === "approve" ? "executed" : "denied", result: redact(result), continuation });
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
