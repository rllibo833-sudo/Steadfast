import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const reply = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { ...cors, "Content-Type": "application/json" } });

type Finding = { severity: "critical" | "high" | "medium" | "low" | "info"; skill: string; title: string; evidence: string; recommendation: string; path?: string };
const file = (paths: string[], regex: RegExp) => paths.find(p => regex.test(p));
const has = (paths: string[], regex: RegExp) => paths.some(p => regex.test(p));

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return reply({ error: "POST required" }, 405);

  const base = Deno.env.get("SUPABASE_URL");
  const key = Deno.env.get("SUPABASE_ANON_KEY") ?? Deno.env.get("SUPABASE_PUBLISHABLE_KEY");
  if (!base || !key) return reply({ error: "Supabase function environment is incomplete." }, 500);

  const auth = req.headers.get("Authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply({ error: "Sign-in required." }, 401);

  try {
    const userRes = await fetch(base + "/auth/v1/user", { headers: { apikey: key, Authorization: auth } });
    if (!userRes.ok) return reply({ error: "Invalid or expired session." }, 401);
    const user = await userRes.json();
    const input = await req.json();
    const taskId = String(input.task_id ?? "");
    const workspaceId = String(input.knowledge_workspace_id ?? "");

    // Shared knowledge writes use the service role only on the server, after checking workspace membership.
    if (input.action === "manual_node" || input.action === "manual_relation") {
      const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
      if (!serviceKey) return reply({ error: "SUPABASE_SERVICE_ROLE_KEY is missing from Supabase Edge Function secrets." }, 500);
      if (!/^[0-9a-f-]{36}$/i.test(workspaceId)) return reply({ error: "Valid knowledge_workspace_id required." }, 400);
      const adminHeaders = { apikey: serviceKey, Authorization: "Bearer " + serviceKey, "Content-Type": "application/json" };
      const workspaceRes = await fetch(base + "/rest/v1/knowledge_workspaces?id=eq." + encodeURIComponent(workspaceId) + "&select=id,owner_id&limit=1", { headers: adminHeaders });
      if (!workspaceRes.ok) return reply({ error: "Could not verify shared workspace." }, 502);
      const workspaces = await workspaceRes.json();
      const workspace = workspaces[0];
      if (!workspace) return reply({ error: "Shared workspace not found." }, 404);
      if (workspace.owner_id !== user.id) {
        const memberRes = await fetch(base + "/rest/v1/knowledge_workspace_members?workspace_id=eq." + encodeURIComponent(workspaceId) + "&user_id=eq." + encodeURIComponent(user.id) + "&select=role&limit=1", { headers: adminHeaders });
        if (!memberRes.ok) return reply({ error: "Could not verify workspace membership." }, 502);
        if (!(await memberRes.json()).length) return reply({ error: "You are not a member of this shared workspace." }, 403);
      }
      const dispatchSync = async () => {
        const token = Deno.env.get("MNEMOS_GITHUB_TOKEN");
        const target = Deno.env.get("MNEMOS_GITHUB_REPOSITORY") ?? "rllibo833-sudo/mnemos-RLI";
        if (!token) return { queued: false, reason: "MNEMOS_GITHUB_TOKEN is not configured; saved in Supabase only." };
        const response = await fetch("https://api.github.com/repos/" + target + "/dispatches", {
          method: "POST",
          headers: { Accept: "application/vnd.github+json", Authorization: "Bearer " + token, "Content-Type": "application/json", "User-Agent": "Steadfast-Knowledge-Sync" },
          body: JSON.stringify({ event_type: "sync-supabase-to-knowledge", client_payload: { workspace_id: workspaceId, actor_id: user.id, manual: true } }),
        });
        return response.ok ? { queued: true } : { queued: false, reason: "GitHub dispatch returned HTTP " + response.status };
      };
      if (input.action === "manual_node") {
        const title = String(input.title ?? "").trim().slice(0, 180);
        const content = String(input.content ?? "").trim().slice(0, 12000);
        const kind = String(input.kind ?? "insight").trim().slice(0, 80) || "insight";
        if (!title || !content) return reply({ error: "Node title and content are required." }, 400);
        const id = "sf-" + crypto.randomUUID();
        const canonical = (s: string) => String(s ?? "").normalize("NFKC").toLocaleLowerCase("id-ID").replace(/\s+/g, " ").replace(/[“”„]/g, '"').replace(/[‘’]/g, "'").trim();
        const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical(title) + "\n" + canonical(content)));
        const contentHash = Array.from(new Uint8Array(digest)).map(x => x.toString(16).padStart(2, "0")).join("");
        const nodeRes = await fetch(base + "/rest/v1/knowledge_nodes", {
          method: "POST", headers: { ...adminHeaders, Prefer: "return=minimal" },
          body: JSON.stringify({ owner_id: user.id, workspace_id: workspaceId, id, kind, title, content, source: { type: "user_saved", created_by: user.id }, metadata: { origin: "steadfast-manual", created_by_email: user.email ?? null }, media: {}, content_sha256: contentHash, schema_version: 1 }),
        });
        if (!nodeRes.ok) return reply({ error: "Node write failed: HTTP " + nodeRes.status + " " + (await nodeRes.text()).slice(0, 300) }, 502);

        // Link exact normalized sentences/phrases and every shared meaningful word automatically.
        const stop = new Set("yang dan di ke dari untuk pada dengan adalah itu ini atau dalam sebagai oleh akan bisa tidak juga sudah agar jika saat setelah sebelum antara sebuah suatu the and for with from that this those these are was were into onto about over under then than have has had not but you your our their they them its can will would should may might a an of to in on at by as is be or it we he she gw gua gue lu lo aku saya kamu dia para setiap lebih kurang hanya".split(" "));
        const terms = (value: string) => new Set((canonical(value).normalize("NFKD").replace(/[\u0300-\u036f]/g, "").match(/[a-z0-9][a-z0-9_-]{1,}/g) || []).filter(w => w.length >= 2 && !stop.has(w)));
        const sentences = (value: string) => new Set((String(value ?? "").normalize("NFKC").match(/[^.!?;\n]+[.!?]?/g) || []).map(canonical).filter(s => s.length >= 16));
        const phrases = (value: string) => new Set((String(value ?? "").normalize("NFKC").match(/"[^"]{4,160}"|“[^”]{4,160}”|'[^']{4,160}'|‘[^’]{4,160}’/g) || []).map(canonical));
        const newTerms = terms(title + "\n" + content);
        const newSentences = sentences(title + "\n" + content);
        const newPhrases = phrases(title + "\n" + content);
        const existingRes = await fetch(base + "/rest/v1/knowledge_nodes?select=id,title,content,kind&workspace_id=eq." + encodeURIComponent(workspaceId) + "&deleted_at=is.null&limit=5000", { headers: adminHeaders });
        if (!existingRes.ok) return reply({ error: "Node saved, but existing knowledge could not be scanned for automatic links: HTTP " + existingRes.status }, 502);
        const existingNodes = await existingRes.json();
        const links: any[] = [];
        for (const node of existingNodes) {
          if (!node.id || node.id === id) continue;
          const oldText = String(node.title ?? "") + "\n" + String(node.content ?? "");
          const matchedWords = [...terms(oldText)].filter(w => newTerms.has(w));
          const matchedSentences = [...sentences(oldText)].filter(s => newSentences.has(s));
          const matchedPhrases = [...phrases(oldText)].filter(s => newPhrases.has(s));
          if (matchedWords.length || matchedSentences.length || matchedPhrases.length) {
            links.push({ owner_id: user.id, workspace_id: workspaceId, source_id: id, target_id: node.id, relation: "auto_match", provenance: { type: "normalized_exact_match", algorithm: "nfkc-sentence-phrase-token-v2" }, confidence: matchedSentences.length || matchedPhrases.length ? 1 : 0.8, metadata: { matched_words: matchedWords.slice(0, 40), matched_sentences: matchedSentences.slice(0, 10), matched_phrases: matchedPhrases.slice(0, 10) } });
          }
        }
        for (let offset = 0; offset < links.length; offset += 100) {
          const linkRes = await fetch(base + "/rest/v1/knowledge_links?on_conflict=source_id,target_id,relation", { method: "POST", headers: { ...adminHeaders, Prefer: "resolution=merge-duplicates,return=minimal" }, body: JSON.stringify(links.slice(offset, offset + 100)) });
          if (!linkRes.ok) return reply({ error: "Node saved, but automatic link write failed: HTTP " + linkRes.status + " " + (await linkRes.text()).slice(0, 300), node_id: id }, 502);
        }
        const sync = await dispatchSync();
        return reply({ ok: true, id, action: "manual_node", auto_relations: links.length, matching: "exact normalized words, phrases, and sentences", sync });
      }

      const sourceId = String(input.source_node_id ?? input.source_id ?? "");
      const targetId = String(input.target_node_id ?? input.target_id ?? "");
      const relation = String(input.relation ?? "related_to").trim().slice(0, 100);
      if (!sourceId || !targetId || sourceId === targetId) return reply({ error: "Choose two different nodes." }, 400);
      const nodeCheck = await fetch(base + "/rest/v1/knowledge_nodes?select=id&id=in.(" + encodeURIComponent(sourceId) + "," + encodeURIComponent(targetId) + ")&workspace_id=eq." + encodeURIComponent(workspaceId) + "&deleted_at=is.null", { headers: adminHeaders });
      if (!nodeCheck.ok) return reply({ error: "Could not validate selected nodes." }, 502);
      if ((await nodeCheck.json()).length !== 2) return reply({ error: "Both nodes must belong to this shared workspace." }, 400);
      const linkRes = await fetch(base + "/rest/v1/knowledge_links?on_conflict=source_id,target_id,relation", { method: "POST", headers: { ...adminHeaders, Prefer: "resolution=merge-duplicates,return=minimal" }, body: JSON.stringify({ owner_id: user.id, workspace_id: workspaceId, source_id: sourceId, target_id: targetId, relation, provenance: { type: "user_defined" }, confidence: 1, metadata: {} }) });
      if (!linkRes.ok) return reply({ error: "Relation write failed: HTTP " + linkRes.status + " " + (await linkRes.text()).slice(0, 300) }, 502);
      const sync = await dispatchSync();
      return reply({ ok: true, action: "manual_relation", sync });
    }

    if (!/^[0-9a-f-]{36}$/i.test(taskId)) return reply({ error: "Valid task_id required." }, 400);

    const headers = { apikey: key, Authorization: auth, "Content-Type": "application/json" };
    const taskRes = await fetch(base + "/rest/v1/steadfast_tasks?id=eq." + encodeURIComponent(taskId) + "&select=id,goal,workspace_id,status,created_by", { headers });
    if (!taskRes.ok) return reply({ error: "Could not read task." }, 403);
    const task = (await taskRes.json())[0];
    if (!task || task.status === "cancelled") return reply({ error: "Task not found or cancelled." }, 404);
    if (task.created_by && task.created_by !== user.id) return reply({ error: "Task does not belong to this user." }, 403);

    const urlMatch = String(task.goal ?? "").match(/https?:\/\/github\.com\/[^\s"<>]+/i);
    if (!urlMatch) return reply({ error: "Put a GitHub repository URL in the task goal." }, 400);
    let parsedRepoUrl: URL;
    try { parsedRepoUrl = new URL(urlMatch[0].replace(/[.,!?;:]+$/, "")); } catch { return reply({ error: "Invalid GitHub repository URL." }, 400); }
    if (parsedRepoUrl.hostname.toLowerCase() !== "github.com") return reply({ error: "Only github.com repository URLs are supported." }, 400);
    const repoParts = parsedRepoUrl.pathname.split("/").filter(Boolean);
    if (repoParts.length < 2) return reply({ error: "Repository URL must include owner and repository." }, 400);
    const owner = repoParts[0];
    const repo = repoParts[1].replace(/\.git$/i, "").replace(/[.,!?;:]+$/, "");
    const repoUrl = "https://github.com/" + owner + "/" + repo;
    const ghHeaders = { Accept: "application/vnd.github+json", "User-Agent": "Steadfast-Repository-Auditor" };

    const patchTask = async (data: unknown) => fetch(base + "/rest/v1/steadfast_tasks?id=eq." + encodeURIComponent(taskId), {
      method: "PATCH", headers: { ...headers, Prefer: "return=minimal" }, body: JSON.stringify(data),
    });
    const addEvent = async (type: string, payload: unknown) => fetch(base + "/rest/v1/steadfast_task_events", {
      method: "POST", headers: { ...headers, Prefer: "return=minimal" },
      body: JSON.stringify({ task_id: taskId, actor_id: user.id, event_type: type, payload }),
    });

    await patchTask({ status: "running", error: null, updated_at: new Date().toISOString() });
    await addEvent("agent.started", { engine: "steadfast-native-skills", repository_url: repoUrl });

    const metaRes = await fetch("https://api.github.com/repos/" + encodeURIComponent(owner) + "/" + encodeURIComponent(repo), { headers: ghHeaders });
    if (!metaRes.ok) {
      const error = metaRes.status === 404 ? "Repository not found or private. Steadfast currently audits public GitHub repositories without a GitHub token." : "GitHub API returned HTTP " + metaRes.status + ".";
      await patchTask({ status: "failed", error, updated_at: new Date().toISOString() });
      await addEvent("agent.failed", { error, repository_url: repoUrl });
      return reply({ error, repository_url: repoUrl }, 502);
    }
    const meta = await metaRes.json();
    const branch = String(meta.default_branch || "main");
    const treeRes = await fetch("https://api.github.com/repos/" + encodeURIComponent(owner) + "/" + encodeURIComponent(repo) + "/git/trees/" + encodeURIComponent(branch) + "?recursive=1", { headers: ghHeaders });
    if (!treeRes.ok) {
      const error = "Could not inspect repository tree (HTTP " + treeRes.status + ").";
      await patchTask({ status: "failed", error, updated_at: new Date().toISOString() });
      await addEvent("agent.failed", { error, repository_url: repoUrl });
      return reply({ error, repository_url: repoUrl }, 502);
    }
    const tree = await treeRes.json();
    const paths: string[] = (tree.tree ?? []).filter((x: any) => x.type === "blob").map((x: any) => String(x.path));
    const workflows = paths.filter(p => /^\.github\/workflows\/[^/]+\.(yml|yaml)$/i.test(p));
    const manifests = paths.filter(p => /(^|\/)(package\.json|pyproject\.toml|Cargo\.toml|go\.mod|requirements\.txt|pom\.xml|build\.gradle|composer\.json)$/i.test(p));
    const lockfiles = paths.filter(p => /(^|\/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|uv\.lock|Cargo\.lock|go\.sum|Pipfile\.lock|composer\.lock)$/i.test(p));
    const selectedChecks = ["repository-health", "ci-governance", "supply-chain-security", "dependency-hygiene", "release-readiness", "documentation-and-security"];
    const selected = [...new Set([...workflows.slice(0, 12), ...manifests.slice(0, 8), ...paths.filter(p => /(^|\/)(CODEOWNERS|SECURITY\.md|CONTRIBUTING\.md|README\.md|dependabot\.yml)$/i.test(p)).slice(0, 8)])].slice(0, 24);
    const evidence: { path: string; content: string }[] = [];
    for (const path of selected) {
      try {
        const url = "https://raw.githubusercontent.com/" + owner + "/" + repo + "/" + encodeURIComponent(branch) + "/" + path.split("/").map(encodeURIComponent).join("/");
        const res = await fetch(url, { headers: ghHeaders });
        if (res.ok) evidence.push({ path, content: (await res.text()).slice(0, 12000) });
      } catch { /* keep auditing remaining evidence */ }
    }

    const findings: Finding[] = [];
    const workflowEvidence = evidence.filter(e => /^\.github\/workflows\//.test(e.path));
    if (!workflows.length) findings.push({ severity: "medium", skill: "ci-governance", title: "No GitHub Actions workflows found", evidence: "Repository tree contains no .github/workflows YAML files.", recommendation: "Add CI checks for tests, linting, and security appropriate to this project." });
    for (const e of workflowEvidence) {
      const body = e.content;
      if (!/^\s*permissions\s*:/m.test(body)) findings.push({ severity: "medium", skill: "ci-governance", title: "Workflow does not declare explicit permissions", path: e.path, evidence: "No top-level permissions: declaration detected in the scanned workflow text.", recommendation: "Declare least-privilege GITHUB_TOKEN permissions at workflow or job level." });
      if (/\bpermissions\s*:\s*write-all\b/i.test(body)) findings.push({ severity: "high", skill: "ci-governance", title: "Workflow grants write-all permissions", path: e.path, evidence: "Detected permissions: write-all.", recommendation: "Replace broad write access with only the permissions required by each job." });
      if (/pull_request_target/i.test(body) && /actions\/checkout@[^\n]+/i.test(body)) findings.push({ severity: "high", skill: "actions-supply-chain", title: "Review privileged pull_request_target workflow", path: e.path, evidence: "Workflow combines pull_request_target with checkout; verify untrusted PR code is never executed with privileged credentials.", recommendation: "Avoid checking out and executing untrusted PR code in privileged workflows; pin actions to full commit SHAs." });
      for (const match of body.matchAll(/uses:\s*([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)@(v?\d+(?:\.\d+){0,2}|main|master|latest)\b/g)) {
        findings.push({ severity: "medium", skill: "actions-supply-chain", title: "Third-party action is not pinned to a full commit SHA", path: e.path, evidence: "Observed " + match[0] + ".", recommendation: "Pin action references to verified full commit SHAs and use Dependabot to manage updates." });
      }
      if (/\bsecrets\.[A-Z0-9_]+/i.test(body) && /pull_request_target/i.test(body)) findings.push({ severity: "high", skill: "actions-supply-chain", title: "Secrets referenced in a privileged pull-request workflow", path: e.path, evidence: "Workflow references secrets and pull_request_target; this is a review signal, not proof of exposure.", recommendation: "Confirm untrusted pull requests cannot access or exfiltrate secrets." });
    }
    if (manifests.length && !lockfiles.length) findings.push({ severity: "medium", skill: "dependency-hygiene", title: "Dependency manifests found without a recognized lockfile", evidence: "Manifests: " + manifests.slice(0, 8).join(", "), recommendation: "Commit the ecosystem's lockfile and use deterministic dependency installation." });
    if (!has(paths, /(^|\/)(SECURITY\.md)$/i)) findings.push({ severity: "low", skill: "documentation-and-security", title: "No SECURITY.md policy detected", evidence: "No SECURITY.md file found in the repository tree.", recommendation: "Publish a vulnerability reporting policy if this repository accepts external contributions or ships software." });
    if (!has(paths, /(^|\/)(CODEOWNERS)$/i) && !has(paths, /(^|\/)\.github\/CODEOWNERS$/i)) findings.push({ severity: "low", skill: "repository-health", title: "No CODEOWNERS file detected", evidence: "No root or .github/CODEOWNERS file found.", recommendation: "Define review ownership for critical code and workflow changes if maintainership requires it." });
    if (!has(paths, /(^|\/)(README\.md)$/i)) findings.push({ severity: "low", skill: "documentation-and-security", title: "No README.md detected", evidence: "Repository tree contains no README.md.", recommendation: "Document purpose, setup, usage, and verification steps." });
    if (tree.truncated) findings.push({ severity: "info", skill: "repository-health", title: "GitHub tree response was truncated", evidence: "GitHub marked the recursive tree as truncated; not every repository path may have been inspected.", recommendation: "Treat this report as partial and inspect important subdirectories separately." });
    if (!findings.length) findings.push({ severity: "info", skill: "repository-health", title: "No configured heuristic triggered", evidence: "The selected deterministic checks did not identify a finding in the inspected evidence.", recommendation: "Review the evidence bundle and add project-specific checks as needed." });

    const count = (severity: string) => findings.filter(f => f.severity === severity).length;
    const summary = "Steadfast native audit inspected " + paths.length + " repository files and " + evidence.length + " evidence files. Found " + findings.length + " review signals (" + count("critical") + " critical, " + count("high") + " high, " + count("medium") + " medium, " + count("low") + " low). No external LLM or paid AI API was used.";
    const result = {
      summary,
      engine: "steadfast-native-skills",
      model_used: null,
      repository: { url: repoUrl, full_name: meta.full_name, description: meta.description || "", default_branch: branch, stars: meta.stargazers_count, private: meta.private },
      selected_skills: selectedChecks,
      checks: { repository_files: paths.length, evidence_files: evidence.length, workflow_files: workflows.length, dependency_manifests: manifests.length, lockfiles: lockfiles.length, tree_truncated: !!tree.truncated },
      findings,
      evidence: evidence.map(e => ({ path: e.path, excerpt: e.content.slice(0, 5000) })),
      plan: ["Review high-severity workflow and supply-chain findings first.", "Confirm dependency lockfiles and deterministic installation.", "Add missing repository security and ownership guidance where appropriate."],
      completed: ["Fetched public repository metadata and recursive tree.", "Selected and ran Steadfast native audit skill packs.", "Collected evidence excerpts and generated findings without a paid AI provider."],
      blockers: [],
      next_actions: findings.some(f => f.severity === "high" || f.severity === "critical") ? ["Resolve high-severity findings and rerun the audit."] : ["Review findings, then rerun after repository changes."],
    };

    await patchTask({ status: "succeeded", result, plan: result.plan, error: null, updated_at: new Date().toISOString() });
    await addEvent("agent.finished", { status: "succeeded", engine: result.engine, summary });
    let saved = 0;
    if (/^[0-9a-f-]{36}$/i.test(workspaceId)) {
      const memories = [
        { title: meta.full_name + " — Steadfast audit", kind: "repository_audit", content: JSON.stringify({ summary, repository: result.repository, checks: result.checks, finding_count: findings.length, audited_at: new Date().toISOString() }), relation: "audit_summary" },
        ...findings.slice(0, 20).map(f => ({ title: f.title, kind: "audit_finding", content: "Severity: " + f.severity + "\nSkill: " + f.skill + "\nEvidence: " + f.evidence + "\nRecommendation: " + f.recommendation + (f.path ? "\nPath: " + f.path : "") + "\nRepository: " + repoUrl, relation: f.skill })),
      ];
      for (const item of memories) {
        const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(item.content));
        const hash = Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, "0")).join("");
        const wr = await fetch(base + "/rest/v1/knowledge_nodes", {
          method: "POST", headers: { ...headers, Prefer: "return=minimal" },
          body: JSON.stringify({ owner_id: user.id, workspace_id: workspaceId, id: "sf-" + crypto.randomUUID(), kind: item.kind, title: item.title.slice(0, 180), content: item.content.slice(0, 12000), source: { type: "steadfast-native-skills", task_id: taskId, repository_url: repoUrl }, metadata: { relation_hint: item.relation, generated_by: "steadfast-native-skills" }, media: {}, content_sha256: hash, schema_version: 1 }),
        });
        if (wr.ok) saved++;
      }
    }
    return reply({ task_id: taskId, status: "succeeded", result, repository_audit: { repository_url: repoUrl, files_scanned: paths.length, evidence_files: evidence.length, findings: findings.length }, shared_memories_saved: saved, engine: "steadfast-native-skills" });
  } catch (error) {
    return reply({ error: error instanceof Error ? error.message : "Unexpected native audit error." }, 500);
  }
});