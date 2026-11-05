import test from "node:test";
import assert from "node:assert/strict";
import { BUSINESS_AGENT_ROLES, containsUnsupportedUrls, extractScoutEvidence, shouldRunBusinessTeam } from "../src/agent-team.ts";

test("business research tasks use distinct specialist roles", () => {
  assert.deepEqual(BUSINESS_AGENT_ROLES.map((role) => role.id), [
    "market-scout", "unit-economics", "risk-reviewer",
  ]);
  assert.equal(shouldRunBusinessTeam("Cari peluang SaaS dengan pengguna dan pemasukan"), true);
});

test("ordinary tasks and execution requests do not invoke the research team", () => {
  assert.equal(shouldRunBusinessTeam("Jelaskan cara membaca log ini"), false);
  assert.equal(shouldRunBusinessTeam("Cari peluang SaaS lalu deploy sekarang"), false);
});

test("scout evidence is taken from read-only tool results, not its prose", () => {
  const evidence = extractScoutEvidence({
    text: "Invented claim",
    steps: [{ toolResults: [{ toolName: "github_search", output: { url: "https://github.com/example/repo/issues/1", title: "Request" } }] }],
  });
  assert.equal(evidence.length, 1);
  assert.match(evidence[0], /github_search/);
  assert.equal(containsUnsupportedUrls("See https://github.com/fake/repo", evidence), true);
  assert.equal(containsUnsupportedUrls("See https://github.com/example/repo/issues/1", evidence), false);
});

test("empty scout tool results stay empty even if the model writes a confident answer", () => {
  assert.deepEqual(extractScoutEvidence({ text: "Seven buyers asked for this" }), []);
});
