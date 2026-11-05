import test from "node:test";
import assert from "node:assert/strict";
import { runFreeFirst } from "../src/provider-routing.ts";

const noProvider = [];

test("uses OpenRouter Free after Cloudflare AI quota exhaustion", async () => {
  const result = await runFreeFirst(
    async () => { throw new Error("Workers AI 429 quota exceeded"); },
    [{ id: "openrouter-free", available: true, run: async () => "openrouter response" }],
  );
  assert.deepEqual(result, { provider: "openrouter-free", value: "openrouter response" });
});

test("recognizes Cloudflare's observed daily neuron allocation error", async () => {
  const result = await runFreeFirst(
    async () => { throw new Error("you have used up your daily free allocation of 10,000 neurons"); },
    [{ id: "openrouter-free", available: true, run: async () => "openrouter response" }],
  );
  assert.equal(result.provider, "openrouter-free");
});

test("skips unconfigured fallbacks and propagates non-quota primary errors", async () => {
  let fallbackCalls = 0;
  await assert.rejects(runFreeFirst(
    async () => { throw new Error("invalid request"); },
    [{ id: "openrouter-free", available: true, run: async () => { fallbackCalls += 1; return "unexpected"; } }],
  ), /invalid request/);
  const result = await runFreeFirst(async () => "cloudflare response", [
    { id: "openrouter-free", available: false, run: async () => { fallbackCalls += 1; return "unexpected"; } },
  ]);
  assert.equal(result.provider, "cloudflare-ai");
  assert.equal(fallbackCalls, 0);
  assert.deepEqual(noProvider, []);
});

test("uses Groq Free if OpenRouter Free is unavailable", async () => {
  const result = await runFreeFirst(
    async () => { throw new Error("daily free allocation exhausted"); },
    [
      { id: "openrouter-free", available: true, run: async () => { throw Object.assign(new Error("rate limit"), { statusCode: 429 }); } },
      { id: "groq-free", available: true, run: async () => "groq response" },
    ],
  );
  assert.deepEqual(result, { provider: "groq-free", value: "groq response" });
});

test("uses Groq Free if OpenRouter credentials are rejected", async () => {
  const result = await runFreeFirst(
    async () => { throw new Error("Cloudflare AI quota exhausted"); },
    [
      { id: "openrouter-free", available: true, run: async () => { throw Object.assign(new Error("Unauthorized"), { statusCode: 401 }); } },
      { id: "groq-free", available: true, run: async () => "groq response" },
    ],
  );
  assert.equal(result.provider, "groq-free");
});

test("propagates the last provider error without a paid fallback", async () => {
  await assert.rejects(runFreeFirst(
    async () => { throw new Error("Cloudflare AI capacity unavailable"); },
    [
      { id: "openrouter-free", available: true, run: async () => { throw Object.assign(new Error("rate limit"), { statusCode: 429 }); } },
      { id: "groq-free", available: true, run: async () => { throw Object.assign(new Error("Groq quota reached"), { statusCode: 429 }); } },
    ],
  ), /Groq quota reached/);
});
