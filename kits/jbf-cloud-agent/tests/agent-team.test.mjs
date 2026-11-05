import test from "node:test";
import assert from "node:assert/strict";
import { BUSINESS_AGENT_ROLES, shouldRunBusinessTeam } from "../src/agent-team.ts";

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
