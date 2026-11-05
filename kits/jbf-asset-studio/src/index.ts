import { DurableObject } from "cloudflare:workers";

interface Env {
  AI: Ai;
  ASSETS: Fetcher;
  QUOTA: DurableObjectNamespace<GenerationQuota>;
}

const MODEL = "@cf/bytedance/stable-diffusion-xl-lightning";
const DAILY_PER_VISITOR = 2;
const DAILY_GLOBAL_CAP = 160;

function json(data: unknown, status = 200): Response {
  return Response.json(data, {
    status,
    headers: { "cache-control": "no-store", "x-content-type-options": "nosniff" },
  });
}

async function dailyKey(request: Request): Promise<string> {
  const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
  const day = new Date().toISOString().slice(0, 10);
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${day}:${ip}`));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export class GenerationQuota extends DurableObject<Env> {
  async fetch(request: Request): Promise<Response> {
    const { visitor, day, operation } = await request.json() as {
      visitor: string; day: string; operation?: "reserve" | "refund";
    };
    const globalKey = `global:${day}`;
    const visitorKey = `visitor:${day}:${visitor}`;
    let global = await this.ctx.storage.get<number>(globalKey) ?? 0;
    let count = await this.ctx.storage.get<number>(visitorKey) ?? 0;

    if (operation === "refund") {
      global = Math.max(0, global - 1);
      count = Math.max(0, count - 1);
      await this.ctx.storage.put(globalKey, global);
      await this.ctx.storage.put(visitorKey, count);
      return json({ refunded: true });
    }
    if (count >= DAILY_PER_VISITOR) return json({ error: "visitor_limit" }, 429);
    if (global >= DAILY_GLOBAL_CAP) return json({ error: "daily_capacity" }, 429);
    global += 1;
    count += 1;
    await this.ctx.storage.put(globalKey, global);
    await this.ctx.storage.put(visitorKey, count);
    return json({ allowed: true, remaining: DAILY_PER_VISITOR - count });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/api/generate" && request.method === "POST") {
      let body: { prompt?: unknown; style?: unknown };
      try { body = await request.json() as typeof body; }
      catch { return json({ error: "Isi prompt gambar yang valid." }, 400); }
      const prompt = typeof body.prompt === "string" ? body.prompt.trim().slice(0, 800) : "";
      const style = typeof body.style === "string" ? body.style : "game";
      if (prompt.length < 4) return json({ error: "Prompt minimal 4 karakter." }, 400);

      const styleText: Record<string, string> = {
        game: "2D indie game asset concept art, clear silhouette, polished game art,",
        pixel: "pixel art game asset, crisp pixels, limited cohesive palette, no blur,",
        portrait: "stylized character portrait illustration for a game, expressive face,",
        world: "indie game environment concept art, readable composition,",
        product: "clean commercial product illustration, studio lighting,",
      };
      const day = new Date().toISOString().slice(0, 10);
      const visitor = await dailyKey(request);
      const quotaStub = env.QUOTA.get(env.QUOTA.idFromName("daily-image-budget"));
      const reservation = await quotaStub.fetch("https://quota/reserve", {
        method: "POST", body: JSON.stringify({ visitor, day }),
      });
      const quota = await reservation.json() as { remaining?: number; error?: string };
      if (!reservation.ok) {
        return json({ error: quota.error === "visitor_limit"
          ? "Kuota gratis hari ini habis (2 gambar per pengunjung). Coba lagi besok."
          : "Kuota harian bersama sedang penuh. Coba lagi besok." }, 429);
      }

      try {
        const image = await env.AI.run(MODEL, {
          prompt: `${styleText[style] ?? styleText.game} ${prompt}`,
          negative_prompt: "text, watermark, logo, blurry, low quality",
          width: 1024, height: 1024, num_steps: 4, guidance: 0,
          seed: crypto.getRandomValues(new Uint32Array(1))[0],
        });
        return new Response(image as ReadableStream<Uint8Array>, {
          headers: {
            "content-type": "image/png", "cache-control": "no-store",
            "x-images-remaining": String(quota.remaining ?? 0),
            "x-content-type-options": "nosniff",
          },
        });
      } catch (error) {
        await quotaStub.fetch("https://quota/refund", {
          method: "POST", body: JSON.stringify({ visitor, day, operation: "refund" }),
        });
        const outOfQuota = /quota|limit|billing|exceeded/i.test(String(error));
        return json({ error: outOfQuota
          ? "Model gambar sedang mencapai batas kapasitas gratis. Tidak ada biaya atau fallback berbayar; coba lagi nanti."
          : "Gambar belum berhasil dibuat. Kuota dikembalikan; coba lagi." }, outOfQuota ? 429 : 502);
      }
    }
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
