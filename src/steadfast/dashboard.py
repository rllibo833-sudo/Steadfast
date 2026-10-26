from __future__ import annotations

import json
import mimetypes
import os
import secrets
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .checks import evidence_findings, run_audit
from .goals import goal_report
from .inventory import inventory_report
from .policy import load_policy
from .release import release_report
from .security import security_findings, workflow_findings
from .workcycle import attach_evidence, block_cycle, complete_cycle, cycle_history, cycle_status, start_cycle, verify_cycle
from .findings import finding_metrics, list_findings
from .planner import execution_plan
from .automations import automation_history, list_automations, run_automation

APP_VERSION = "0.2.0"
MAX_FILE_BYTES = 256_000
TEXT_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs",
    ".java", ".c", ".h", ".cpp", ".hpp", ".cuk", ".sh", ".yaml", ".yml",
    ".toml", ".json", ".md", ".html", ".css", ".sql", ".xml", ".txt",
    ".ini", ".cfg", ".env.example",
}
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".tox",
}


def _safe_relative(repo: Path, value: str) -> Path:
    candidate = (repo / value).resolve()
    try:
        candidate.relative_to(repo.resolve())
    except ValueError as exc:
        raise ValueError("Path escapes repository root") from exc
    return candidate


def _walk_files(repo: Path, limit: int = 5000) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    root = repo.resolve()
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(
            d for d in dirs
            if d not in SKIP_DIRS and not (current_path / d).is_symlink()
        )
        for filename in sorted(files):
            path = current_path / filename
            if path.is_symlink():
                continue
            try:
                stat = path.stat()
                rel = path.relative_to(root).as_posix()
            except OSError:
                continue
            if rel == ".git" or rel.startswith(".git/"):
                continue
            items.append({
                "path": rel,
                "size": stat.st_size,
                "modified": int(stat.st_mtime),
                "kind": path.suffix.lower().lstrip(".") or "file",
            })
            if len(items) >= limit:
                return items
    return items


def _read_json_if_present(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def build_snapshot(repo: Path) -> dict[str, object]:
    """Build a fresh, read-only project snapshot using the existing product engine."""
    repo = repo.resolve()
    policy = load_policy(repo)
    audit = run_audit(repo)
    security = security_findings(repo, policy) + workflow_findings(repo)
    evidence = evidence_findings(repo, policy)
    goals = goal_report(repo, policy)
    release = release_report(repo)
    inventory = inventory_report(repo)
    files = _walk_files(repo)
    severity = Counter(str(item.get("severity", "info")) for item in security + evidence + goals.get("findings", []))
    try:
        agent_sessions = session_report(repo, limit=12)
    except (SessionLedgerError, OSError, ValueError) as exc:
        agent_sessions = {"ledger": ".steadfast/agent-sessions.jsonl", "integrity": "invalid", "error": str(exc), "total_events": 0, "returned_events": 0, "decisions": {}, "tools": {}, "sessions": [], "events": []}
    return {
        "product": "Steadfast",
        "version": APP_VERSION,
        "root": str(repo),
        "generated_at": int(time.time()),
        "audit": audit,
        "security": {"findings": security, "count": len(security)},
        "evidence": {"findings": evidence, "count": len(evidence)},
        "goals": goals,
        "release": release,
        "inventory": inventory,
        "files": files,
        "file_count": len(files),
        "severity": dict(severity),
        "execution_plan": execution_plan(repo),
        "work_cycle": cycle_status(repo),
        "work_cycle_history": cycle_history(repo, limit=8),
        "finding_ledger": list_findings(repo, limit=25),
        "finding_metrics": finding_metrics(repo),
    }


def _page(token: str) -> bytes:
    return _HTML.replace("__STEADFAST_ACTION_TOKEN__", token).encode("utf-8")


_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="dark light">
<title>Steadfast · Project Console</title>
<style>
:root{color-scheme:dark;--bg:#10131a;--panel:#191e29;--panel2:#202736;--text:#edf1f8;--muted:#a6b0c2;--line:#30394b;--accent:#8db7ff;--good:#70d7a1;--warn:#f2c879;--bad:#ff8d94}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,sans-serif}
button,input{font:inherit}button{border:1px solid var(--line);background:var(--panel2);color:var(--text);padding:9px 12px;border-radius:10px;cursor:pointer}button:hover{border-color:var(--accent)}button:focus-visible,a:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px max(16px,calc((100vw - 1400px)/2));border-bottom:1px solid var(--line);position:sticky;top:0;background:#10131aee;backdrop-filter:blur(12px);z-index:3}
.brand{display:flex;align-items:center;gap:12px}.mark{width:36px;height:36px;border-radius:12px;background:var(--accent);color:#10203a;display:grid;place-items:center;font-weight:900;font-size:19px}.brand strong{font-size:17px}.brand small{display:block;color:var(--muted);font-size:12px}
.wrap{max-width:1400px;margin:auto;padding:24px 18px 60px}.intro{display:flex;justify-content:space-between;align-items:end;gap:18px;margin-bottom:20px}.eyebrow{color:var(--accent);text-transform:uppercase;letter-spacing:.12em;font-size:11px;font-weight:800}.intro h1{font-size:clamp(25px,4vw,38px);line-height:1.15;margin:5px 0 8px}.sub{color:var(--muted);margin:0;overflow-wrap:anywhere}.actions{display:flex;gap:8px;flex-wrap:wrap}
.status{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);padding:5px 9px;border-radius:99px;font-size:12px}.dot{width:7px;height:7px;border-radius:50%;background:var(--good)}.dot.bad{background:var(--bad)}.dot.warn{background:var(--warn)}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px}.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:17px;min-width:0}.metric{grid-column:span 3;min-height:124px}.metric label{display:block;color:var(--muted);font-size:12px}.metric strong{display:block;font-size:31px;line-height:1.2;margin:9px 0 4px;overflow-wrap:anywhere}.metric small{color:var(--muted)}.wide{grid-column:span 8}.side{grid-column:span 4}.full{grid-column:1/-1}.card h2{font-size:16px;margin:0 0 14px}.section-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.muted{color:var(--muted)}.pill{font-size:11px;padding:3px 8px;border-radius:99px;background:var(--panel2);border:1px solid var(--line)}.pill.good{color:var(--good)}.pill.warn{color:var(--warn)}.pill.bad{color:var(--bad)}
.rows{display:grid;gap:8px}.rowitem{padding:11px 0;border-top:1px solid var(--line);display:flex;align-items:start;justify-content:space-between;gap:12px}.rowitem:first-child{border-top:0}.rowitem b{display:block;font-size:13px;overflow-wrap:anywhere}.rowitem small{display:block;color:var(--muted);margin-top:3px;overflow-wrap:anywhere}.empty{padding:18px 0;color:var(--muted);text-align:center}.split{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.mini{background:var(--panel2);border-radius:10px;padding:12px}.mini strong{display:block;font-size:22px}.mini small{color:var(--muted)}
.bar{height:8px;border-radius:20px;background:var(--panel2);overflow:hidden;margin:12px 0}.bar span{height:100%;display:block;background:var(--accent);width:0;transition:width .25s}
.search{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--line);padding:10px 12px;border-radius:10px;margin-bottom:10px}.file-list{max-height:470px;overflow:auto}.file{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:9px 5px;border-bottom:1px solid var(--line);cursor:pointer}.file:hover{background:var(--panel2)}.file code{font-size:12px;overflow-wrap:anywhere}.file small{color:var(--muted);white-space:nowrap}.viewer{min-height:120px;max-height:470px;overflow:auto;background:var(--bg);border:1px solid var(--line);padding:13px;border-radius:10px;white-space:pre;tab-size:4;font:12px/1.6 ui-monospace,SFMono-Regular,monospace}
.finding{padding:12px 0;border-top:1px solid var(--line)}.finding:first-child{border-top:0}.finding .top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.finding b{font-size:13px}.finding p{margin:5px 0 0;color:var(--muted);font-size:13px}.finding code{font-size:12px;color:var(--accent);overflow-wrap:anywhere}
footer{margin-top:22px;color:var(--muted);font-size:12px;text-align:center}.notice{border:1px solid var(--line);background:var(--panel);padding:12px;border-radius:10px;color:var(--muted);margin-bottom:14px}
@media(max-width:900px){.metric{grid-column:span 6}.wide,.side{grid-column:span 12}.intro{align-items:start;flex-direction:column}.wrap{padding-top:18px}}
@media(max-width:430px){header{padding:12px}.metric{grid-column:span 6;padding:13px;min-height:112px}.metric strong{font-size:26px}.card{padding:14px}.split{grid-template-columns:1fr 1fr}.actions button{flex:1}}
</style>
</head>
<body>
<header><div class="brand"><div class="mark">S</div><div><strong>Steadfast</strong><small>Project quality console</small></div></div><div class="actions"><span id="live" class="status"><span class="dot"></span> Local console</span><button id="refresh">Refresh scan</button></div></header>
<main class="wrap">
<section class="intro"><div><div class="eyebrow">Repository intelligence</div><h1>Project overview</h1><p class="sub" id="root">Connecting to local workspace…</p></div><div class="actions"><button data-tab="findings">Review findings</button><button data-tab="files">Browse source</button></div></section>
<div id="notice" class="notice" hidden></div>
<section class="grid">
<div class="card metric"><label>Overall audit</label><strong id="auditState">—</strong><small id="auditHint">Waiting for scan</small></div>
<div class="card metric"><label>Security findings</label><strong id="securityCount">—</strong><small id="securityHint">Source and workflow scan</small></div>
<div class="card metric"><label>Repository files</label><strong id="fileCount">—</strong><small id="fileHint">Readable workspace inventory</small></div>
<div class="card metric"><label>Release readiness</label><strong id="releaseState">—</strong><small id="releaseHint">Evidence-based gate</small></div>
<div class="card full" id="planPanel"><div class="section-head"><h2>Next work to execute</h2><span id="planCount" class="pill">0 ready</span></div><div id="planBody" class="rows"><div class="empty">Loading execution plan…</div></div><small class="muted">Recommendations respect goal dependencies. Risk matching is heuristic; it does not prove causality.</small></div>
<div class="card full" id="automationPanel"><div class="section-head"><h2>Automation Studio</h2><span class="pill">Local · no API key</span></div><p class="muted">Run built-in project workflows with one tap. These use fixed local actions; no arbitrary shell commands or repository uploads.</p><div id="automationList" class="rows"><div class="empty">Loading local automations…</div></div><p id="automationMessage" class="muted" role="status" aria-live="polite"></p><div class="section-head" style="margin-top:14px"><h2>Recent automation runs</h2><span id="automationHistoryCount" class="muted">0 runs</span></div><div id="automationHistory" class="rows"><div class="empty">No runs yet.</div></div></div>
<div class="card full" id="cyclePanel"><div class="section-head"><h2>Work cycle</h2><span id="cycleStatus" class="pill">No task</span></div><p class="muted">Manage the active goal, attach proof, run verification, and close the task only when gates pass.</p><div class="actions" style="margin:12px 0"><form id="cycleStartForm" class="actions"><input id="cycleGoal" placeholder="Goal ID (e.g. goal)" required maxlength="64" aria-label="Goal ID"><input id="cycleTitle" placeholder="Task title (optional)" maxlength="160" aria-label="Task title"><button type="submit">Start task</button></form><button id="cycleVerify" type="button">Run verification</button><button id="cycleComplete" type="button">Complete task</button></div><form id="cycleEvidenceForm" class="actions"><select id="cycleCriterion" aria-label="Acceptance criterion" required><option value="">Select criterion</option></select><input id="cycleEvidencePath" placeholder="Repository file path for evidence" required maxlength="512" aria-label="Evidence file path"><input id="cycleEvidenceNote" placeholder="Evidence note (optional)" maxlength="500" aria-label="Evidence note"><button type="submit">Attach evidence</button></form><form id="cycleBlockForm" class="actions" style="margin-top:10px"><input id="cycleBlockReason" placeholder="Reason to block task" maxlength="500" aria-label="Block reason" required><button type="submit">Block task</button></form><p id="cycleActionMessage" class="muted" role="status" aria-live="polite"></p><div id="cycleBody" class="rows"><div class="empty">No tracked task yet.</div></div><div class="section-head" style="margin-top:14px"><h2>Recent cycle events</h2><span id="cycleEventCount" class="muted">0 events</span></div><div id="cycleEvents" class="rows"><div class="empty">No events recorded.</div></div></div>
<div class="card full" id="agentSessionsPanel"><div class="section-head"><h2>Agent session ledger</h2><span id="agentSessionCount" class="pill">0 events</span></div><p class="muted">Tool decisions recorded by installed agent hooks. Secret-like fields are redacted; verify the append-only hash chain with <code>steadfast sessions verify</code>.</p><div id="agentSessionSummary" class="split"></div><div id="agentSessionRows" class="rows"><div class="empty">No agent hook events recorded yet.</div></div></div>
<div class="card full" id="ledgerPanel"><div class="section-head"><h2>Finding lifecycle</h2><span id="ledgerCount" class="pill">Ledger not scanned</span></div><div id="ledgerMetrics" class="split"></div><div id="ledgerRows" class="rows"><div class="empty">Run <code>steadfast findings scan</code> to create a durable finding ledger.</div></div></div>
<div class="card wide"><div class="section-head"><h2>Quality signals</h2><span id="generated" class="muted">—</span></div><div class="split"><div class="mini"><strong id="errors">—</strong><small>Errors</small></div><div class="mini"><strong id="warnings">—</strong><small>Warnings</small></div><div class="mini"><strong id="goals">—</strong><small>Goal findings</small></div></div><div class="bar"><span id="healthbar"></span></div><p class="muted" id="healthText">A scan summarizes the current workspace.</p></div>
<div class="card side"><h2>Workspace actions</h2><div class="rows"><div class="rowitem"><div><b>Run a fresh scan</b><small>Recompute audit, security, goals and release gates.</small></div><button id="scanAgain">Run</button></div><div class="rowitem"><div><b>Inspect findings</b><small>Filter and review actionable results.</small></div><button data-tab="findings">Open</button></div><div class="rowitem"><div><b>Explore source files</b><small>Read files without changing the repository.</small></div><button data-tab="files">Open</button></div></div></div>
<div class="card wide" id="findingsPanel"><div class="section-head"><h2>Actionable findings</h2><span id="findingTotal" class="pill">0</span></div><input id="findingSearch" class="search" placeholder="Filter by code, file, message…"><div id="findings" class="rows"><div class="empty">Loading findings…</div></div></div>
<div class="card side"><h2>Goal and release gates</h2><div id="gates" class="rows"><div class="empty">Loading gates…</div></div></div>
<div class="card full" id="filesPanel"><div class="section-head"><h2>Source explorer</h2><span class="pill" id="fileTotal">0 files</span></div><div class="grid"><div class="card wide"><input id="fileSearch" class="search" placeholder="Find a file by path…"><div id="fileList" class="file-list"></div></div><div class="card side"><div class="section-head"><h2 id="viewerTitle">File preview</h2><span id="viewerSize" class="muted"></span></div><pre id="viewer" class="viewer">Select a text file to inspect it. Files are never modified.</pre></div></div></div>
</section><footer>Runs on your device · No external service · Task controls enabled · source files unchanged · <span id="footerVersion">Steadfast</span></footer>
</main>
<script>
const $=id=>document.getElementById(id);
const actionToken="__STEADFAST_ACTION_TOKEN__";
let snapshot=null, allFindings=[], files=[];
async function api(path){const r=await fetch(path,{headers:{Accept:"application/json"}});const data=await r.json();if(!r.ok)throw new Error(data.error||("HTTP "+r.status));return data;}
function esc(value){return String(value==null?"":value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function pill(text,kind){return '<span class="pill '+kind+'">'+esc(text)+'</span>';}
function classify(ok){return ok?"good":"bad";}
function renderFinding(f){const sev=String(f.severity||"info").toLowerCase();return '<article class="finding"><div class="top">'+pill(sev,sev==="error"?"bad":sev==="warning"?"warn":"good")+'<b>'+esc(f.code||"FINDING")+'</b></div><p>'+esc(f.message||"No description")+'</p><code>'+esc(f.path||"")+(f.line?" : "+esc(f.line):"")+'</code></article>';}
function setNotice(message){$("notice").hidden=!message;$("notice").textContent=message||"";}
function render(){
 if(!snapshot)return;
 const audit=snapshot.audit||{},sec=snapshot.security||{},rel=snapshot.release||{},goal=snapshot.goals||{};
 $("root").textContent=snapshot.root||"Local repository";
 $("auditState").textContent=audit.passed?"PASS":"REVIEW";
 $("auditHint").textContent=audit.passed?"No blocking audit errors":"Audit has findings to review";
 $("securityCount").textContent=sec.count||0;
 $("securityHint").textContent=(snapshot.severity&&snapshot.severity.error||0)+" errors · "+(snapshot.severity&&snapshot.severity.warning||0)+" warnings";
 $("fileCount").textContent=snapshot.file_count||0;
 $("fileHint").textContent="Up to 5,000 files indexed";
 $("releaseState").textContent=rel.ready?"READY":"BLOCKED";
 $("releaseHint").textContent=rel.ready?"Prerequisites satisfied":"Prerequisites remain unmet";
 const combined=[...(audit.findings||[]),...(sec.findings||[]),...(snapshot.evidence&&snapshot.evidence.findings||[]),...(goal.findings||[])];
 const unique=new Map();combined.forEach(f=>unique.set([f.code,f.path,f.message].join("|"),f));allFindings=[...unique.values()];
 const errors=allFindings.filter(f=>f.severity==="error").length,warnings=allFindings.filter(f=>f.severity==="warning").length;
 $("errors").textContent=errors;$("warnings").textContent=warnings;$("goals").textContent=(goal.findings||[]).length;
 const score=Math.max(0,100-errors*12-warnings*3);$("healthbar").style.width=score+"%";
 $("healthText").textContent=score+" illustrative quality points from "+allFindings.length+" findings; this is a triage aid, not a certification.";
 $("generated").textContent="Updated "+new Date(snapshot.generated_at*1000).toLocaleTimeString();
 $("findingTotal").textContent=allFindings.length+" findings";
 $("footerVersion").textContent="v"+(snapshot.version||"");
 files=snapshot.files||[];$("fileTotal").textContent=files.length+" files";
 renderFindings();renderFiles();renderGates();renderCycle();renderPlan();renderLedger();renderAgentSessions();
}
function renderFindings(){
 const q=$("findingSearch").value.trim().toLowerCase();
 const filtered=allFindings.filter(f=>[f.code,f.path,f.message,f.severity].join(" ").toLowerCase().includes(q));
 $("findingTotal").textContent=filtered.length+" shown";
 $("findings").innerHTML=filtered.length?filtered.slice(0,250).map(renderFinding).join(""):'<div class="empty">No matching findings.</div>';
}
function renderGates(){
 const g=snapshot.goals||{},r=snapshot.release||{},items=[
 ["Goal graph",g.passed?"Valid":"Review",g.passed,"Dependencies and goal contracts"],
 ["Release gate",r.ready?"Ready":"Blocked",r.ready,"Required evidence and policy"],
 ["Security scan",(snapshot.security&&snapshot.security.count||0)+" findings",!(snapshot.security&&snapshot.security.count),"Review source and workflow risks"],
 ["Evidence",(snapshot.evidence&&snapshot.evidence.count||0)+" findings",!(snapshot.evidence&&snapshot.evidence.count),"Required verification records"]
 ];
 $("gates").innerHTML=items.map(x=>'<div class="rowitem"><div><b>'+esc(x[0])+'</b><small>'+esc(x[3])+'</small></div>'+pill(x[1],x[2]?"good":"warn")+'</div>').join("");
}
function renderPlan(){
 const plan=snapshot.execution_plan||{},queue=plan.execution_queue||[];
 $("planCount").textContent=(plan.ready_count||0)+" ready";
 if(!queue.length){
  const errors=plan.graph_errors||[];
  $("planBody").innerHTML=errors.length?errors.map(x=>'<div class="rowitem"><div><b>Dependency graph error</b><small>'+esc(x)+'</small></div></div>').join(""):'<div class="empty">No goals are ready to start. Check goal statuses and dependencies with <code>steadfast plan</code>.</div>';
  return;
 }
 $("planBody").innerHTML=queue.slice(0,8).map(item=>'<div class="rowitem"><div><b>#'+esc(item.execution_rank||"—")+' · '+esc(item.title||item.goal_id)+'</b><small>'+esc(item.goal_id)+' · '+esc(item.goal_path)+' · '+esc(item.acceptance_count)+' acceptance criteria</small><small>'+esc(item.recommended_action)+' · related open-risk weight '+esc(item.risk_score)+'</small></div><span class="pill good">Ready</span></div>').join("");
}
async function loadAutomations(){
 const list=await api("/api/automations"),history=await api("/api/automations/history");
 $("automationList").innerHTML=(list.workflows||[]).map(w=>'<div class="rowitem"><div><b>'+esc(w.name)+'</b><small>'+esc(w.description)+'</small><small>'+esc(w.steps.join(" → "))+'</small></div><button type="button" data-automation="'+esc(w.id)+'">Run</button></div>').join("");
 $("automationList").querySelectorAll("[data-automation]").forEach(button=>button.addEventListener("click",async()=>{
  const id=button.getAttribute("data-automation");button.disabled=true;$("automationMessage").textContent="Running "+id+"…";
  try{const response=await fetch("/api/automations/run",{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json","X-Steadfast-Token":actionToken},body:JSON.stringify({workflow_id:id})});const data=await response.json();if(!response.ok)throw new Error(data.error||("Workflow "+(data.result&&data.result.status||"failed")));const result=data.result;$("automationMessage").textContent=result.workflow_name+": "+result.status+" ("+result.step_count+" steps).";await loadAutomations();}
  catch(e){$("automationMessage").textContent="Automation failed: "+e.message;try{renderAutomationHistory(await api("/api/automations/history"));}catch(_){}}
  finally{button.disabled=false;}
 }));
 renderAutomationHistory(history);
}
function renderAutomationHistory(history){
 const runs=history.runs||[];$("automationHistoryCount").textContent=runs.length+" runs";
 $("automationHistory").innerHTML=runs.length?runs.slice(0,8).map(r=>'<div class="rowitem"><div><b>'+esc(r.workflow_name)+' · '+esc(r.status)+'</b><small>'+esc(r.started_at)+' · '+esc(r.run_id)+'</small><small>'+esc((r.steps||[]).map(x=>x.action+":"+x.status).join(" · "))+'</small></div><span class="pill '+(r.status==="passed"?"good":"bad")+'">'+esc(r.step_count)+' steps</span></div>').join(""):'<div class="empty">No automation runs yet. Choose a workflow above.</div>';
}
function renderCycle(){
 const cycle=snapshot.work_cycle||{},task=cycle.task,events=(snapshot.work_cycle_history||{}).events||[];
 $("cycleStatus").textContent=task?task.status:"No task";
 $("cycleStatus").className="pill "+(task&&task.status==="completed"?"good":task&&task.status==="blocked"?"bad":task?"warn":"");
 if(!task){
  $("cycleBody").innerHTML='<div class="empty">No active task. Start with <code>steadfast cycle start goal</code> from the repository root.</div>';
 }else{
  const summary=task.acceptance_summary||{};
  const verify=task.verification;
  const verifyText=verify?(verify.passed?(task.verification_fresh?"Passed · workspace unchanged":"Stale · workspace changed"):"Failed"):"Not run";
  const rows=[
   ["Task",task.title||task.goal_id,task.goal_id||""],
   ["Acceptance evidence",(summary.with_evidence||0)+" / "+(summary.total||0)+" criteria",summary.missing_evidence&&summary.missing_evidence.length?"Missing: "+summary.missing_evidence.join(", "):"All criteria have evidence attached"],
   ["Latest verification",verifyText,verify&&verify.verified_at?"At "+verify.verified_at:"Pipeline and scope check have not run"],
   ["Changed paths",(task.changed_paths||[]).length+" tracked paths",(task.changed_paths||[]).slice(0,5).join(", ")||"No changed paths recorded"]
  ];
  $("cycleBody").innerHTML=rows.map(x=>'<div class="rowitem"><div><b>'+esc(x[0])+'</b><small>'+esc(x[1])+'</small><small>'+esc(x[2])+'</small></div></div>').join("");
 }
 const criterionSelect=$("cycleCriterion"), previousCriterion=criterionSelect.value;
 const options=task?(task.acceptance||[]).map(x=>'<option value="'+esc(x.id)+'">'+esc(x.id+' · '+x.criterion+(x.evidence?' (evidence attached)':''))+'</option>').join(""):"";
 criterionSelect.innerHTML='<option value="">Select criterion</option>'+options;
 if(previousCriterion && task && task.acceptance.some(x=>x.id===previousCriterion))criterionSelect.value=previousCriterion;
 const active=!!task&&["in_progress","verifying"].includes(task.status);
 $("cycleVerify").disabled=!active;$("cycleComplete").disabled=!active;
 $("cycleBlockForm").querySelector("button").disabled=!active;
 $("cycleStartForm").querySelector("button").disabled=active;
 $("cycleEvidenceForm").querySelector("button").disabled=!active;
 $("cycleEventCount").textContent=events.length+" events";
 $("cycleEvents").innerHTML=events.length?events.slice(0,8).map(e=>'<div class="rowitem"><div><b>'+esc(e.event||"event")+'</b><small>'+esc(e.at||"")+' · '+esc(e.task_id||"")+'</small><small>'+esc(JSON.stringify(e.details||{}))+'</small></div></div>').join(""):'<div class="empty">No events recorded.</div>';
}
function renderAgentSessions(){
 const report=snapshot.agent_sessions||{},sessions=report.sessions||[],events=report.events||[];
 $("agentSessionCount").textContent=(report.total_events||0)+" events";
 const decisions=report.decisions||{};
 $("agentSessionSummary").innerHTML=[
  ["Allowed",decisions.allow||0],["Blocked",decisions.block||0],["Sessions",sessions.length]
 ].map(x=>'<div class="mini"><strong>'+esc(x[1])+'</strong><small>'+esc(x[0])+'</small></div>').join("");
 if(report.integrity==="invalid"){$("agentSessionCount").className="pill bad";$("agentSessionCount").textContent="Ledger invalid";$("agentSessionRows").innerHTML='<div class="finding"><b>Session ledger integrity error</b><p>'+esc(report.error||"Unknown error")+"</p></div>";return;}
 $("agentSessionRows").innerHTML=events.length?events.slice(0,12).map(e=>'<div class="rowitem"><div><b>'+esc(e.tool_name||"unknown tool")+' · '+esc(e.event_name||"event")+' '+(e.decision==="block"?pill("BLOCKED","bad"):pill("ALLOWED","good"))+'</b><small>'+esc(e.at||"")+' · session '+esc(e.session_id||"default")+'</small><small>'+esc((e.paths||[]).join(", ")||e.command_preview||"No path/command metadata")+'</small><small>'+esc((e.finding_codes||[]).join(", ")||"No policy findings")+'</small></div></div>').join(""):'<div class="empty">No agent hook events recorded yet. Install an agent integration and use its hooks to populate this ledger.</div>';
}
function renderLedger(){
 const metrics=snapshot.finding_metrics||{},data=snapshot.finding_ledger||{},items=data.findings||[];
 $("ledgerCount").textContent=metrics.scan_count?metrics.scan_count+" scans · "+(metrics.total||0)+" tracked":"Not scanned";
 const metricRows=[
  ["Open high risk",((metrics.open_by_priority||{}).critical||0)+((metrics.open_by_priority||{}).high||0)],
  ["Accepted risk",metrics.accepted_risk||0],
  ["Overdue",metrics.overdue||0]
 ];
 $("ledgerMetrics").innerHTML=metricRows.map(x=>'<div class="mini"><small>'+esc(x[0])+'</small><strong>'+esc(x[1])+'</strong></div>').join("");
 const order={critical:0,high:1,medium:2,low:3};
 items.sort((a,b)=>(order[a.priority]??2)-(order[b.priority]??2));
 $("ledgerRows").innerHTML=items.length?items.slice(0,12).map(x=>'<div class="rowitem"><div><b>'+esc(x.code||x.id)+' · '+esc(x.path||"")+'</b><small>'+esc(x.message||"")+'</small><small>Owner: '+esc(x.owner||"Unassigned")+' · Due: '+esc(x.due_date||"—")+'</small></div><span class="pill '+(x.state==="fixed"||x.state==="false_positive"?"good":x.priority==="critical"||x.priority==="high"?"bad":"warn")+'">'+esc(x.state)+" / "+esc(x.priority)+'</span></div>').join(""):'<div class="empty">No tracked findings yet. Use <code>steadfast findings scan</code> from the repository root; dashboard reads the ledger without mutating it.</div>';
}
function renderFiles(){
 const q=$("fileSearch").value.trim().toLowerCase();
 const shown=files.filter(f=>f.path.toLowerCase().includes(q)).slice(0,500);
 $("fileList").innerHTML=shown.map(f=>'<div class="file" tabindex="0" role="button" data-path="'+esc(f.path)+'"><code>'+esc(f.path)+'</code><small>'+esc(formatSize(f.size))+'</small></div>').join("")||'<div class="empty">No files match this search.</div>';
}
function formatSize(n){if(n<1024)return n+" B";if(n<1048576)return (n/1024).toFixed(1)+" KB";return (n/1048576).toFixed(1)+" MB";}
async function openFile(path){
 $("viewerTitle").textContent=path;$("viewer").textContent="Loading…";$("viewerSize").textContent="";
 try{const data=await api("/api/file?path="+encodeURIComponent(path));$("viewer").textContent=data.content;$("viewerSize").textContent=formatSize(data.size);}
 catch(e){$("viewer").textContent=e.message;}
}
async function refresh(){
 $("refresh").disabled=true;$("scanAgain").disabled=true;$("live").innerHTML='<span class="dot warn"></span> Scanning…';setNotice("");
 try{snapshot=await api("/api/overview?refresh=1");render();$("live").innerHTML='<span class="dot"></span> Local console';}
 catch(e){setNotice("Scan failed: "+e.message);$("live").innerHTML='<span class="dot bad"></span> Scan failed';}
 finally{$("refresh").disabled=false;$("scanAgain").disabled=false;}
}
async function cycleAction(action,payload){
 $("cycleActionMessage").textContent="Working…";
 const response=await fetch("/api/cycle/"+action,{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json","X-Steadfast-Token":actionToken},body:JSON.stringify(payload||{})});
 const data=await response.json();
 if(!response.ok)throw new Error(data.error||("HTTP "+response.status));
 $("cycleActionMessage").textContent=action==="verify"?(data.result.passed?"Verification passed.":"Verification failed; task remains open."):"Action completed: "+action;
 await refresh();
}
$("cycleStartForm").addEventListener("submit",async e=>{e.preventDefault();try{await cycleAction("start",{goal_id:$("cycleGoal").value.trim(),title:$("cycleTitle").value.trim()});}catch(err){$("cycleActionMessage").textContent=err.message;}});
$("cycleEvidenceForm").addEventListener("submit",async e=>{e.preventDefault();try{await cycleAction("evidence",{criterion_id:$("cycleCriterion").value,path:$("cycleEvidencePath").value.trim(),note:$("cycleEvidenceNote").value.trim()});}catch(err){$("cycleActionMessage").textContent=err.message;}});
$("cycleVerify").addEventListener("click",async()=>{try{await cycleAction("verify",{});}catch(err){$("cycleActionMessage").textContent=err.message;}});
$("cycleComplete").addEventListener("click",async()=>{if(!confirm("Complete this task only if all evidence and verification are correct?"))return;try{await cycleAction("complete",{});}catch(err){$("cycleActionMessage").textContent=err.message;}});
$("cycleBlockForm").addEventListener("submit",async e=>{e.preventDefault();try{await cycleAction("block",{reason:$("cycleBlockReason").value.trim()});}catch(err){$("cycleActionMessage").textContent=err.message;}});
$("refresh").addEventListener("click",refresh);$("scanAgain").addEventListener("click",refresh);
$("findingSearch").addEventListener("input",renderFindings);$("fileSearch").addEventListener("input",renderFiles);
$("fileList").addEventListener("click",e=>{const item=e.target.closest("[data-path]");if(item)openFile(item.dataset.path);});
$("fileList").addEventListener("keydown",e=>{if((e.key==="Enter"||e.key===" ")&&e.target.matches("[data-path]")){e.preventDefault();openFile(e.target.dataset.path);}});
document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>{const target=b.dataset.tab==="files"?$("filesPanel"):$("findingsPanel");target.scrollIntoView({behavior:"smooth",block:"start"});}));
api("/api/overview").then(data=>{snapshot=data;render();$("live").innerHTML='<span class="dot"></span> Local console';}).catch(e=>setNotice("Could not load workspace: "+e.message));
loadAutomations().catch(e=>{$("automationMessage").textContent=e.message;});
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "SteadfastDashboard/0.2"

    @property
    def repo(self) -> Path:
        return self.server.repo  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep terminal output useful and avoid leaking request query values.
        print("[steadfast-dashboard] " + (fmt % args).split("?", 1)[0])

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: object) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send(200, _page(self.server.action_token), "text/html; charset=utf-8")
            return
        if parsed.path == "/health":
            self._json(200, {"ok": True, "product": "Steadfast", "version": APP_VERSION})
            return
        if parsed.path == "/api/automations":
            try:
                self._json(200, list_automations(self.repo))
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
            return
        if parsed.path == "/api/automations/history":
            try:
                self._json(200, automation_history(self.repo, 20))
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
            return
        if parsed.path == "/api/overview":
            try:
                self._json(200, build_snapshot(self.repo))
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
                self._json(500, {"error": str(exc)})
            return
        if parsed.path == "/api/file":
            value = parse_qs(parsed.query).get("path", [""])[0]
            if not value or "\x00" in value:
                self._json(400, {"error": "A repository-relative path is required"})
                return
            try:
                path = _safe_relative(self.repo, value)
                if not path.is_file() or path.is_symlink():
                    self._json(404, {"error": "File not found"})
                    return
                if path.stat().st_size > MAX_FILE_BYTES:
                    self._json(413, {"error": "File is larger than the 256 KB preview limit"})
                    return
                if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {".gitignore", "Makefile", "Dockerfile"}:
                    self._json(415, {"error": "Binary or unsupported file type; preview blocked"})
                    return
                content = path.read_text(encoding="utf-8")
                self._json(200, {"path": path.relative_to(self.repo).as_posix(), "size": path.stat().st_size, "content": content})
            except (ValueError, OSError, UnicodeError) as exc:
                self._json(400, {"error": str(exc)})
            return
        self._json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        is_cycle = parsed.path.startswith("/api/cycle/")
        is_automation = parsed.path == "/api/automations/run"
        if not is_cycle and not is_automation:
            self._json(404, {"error": "Not found"})
            return
        token = self.headers.get("X-Steadfast-Token", "")
        origin, host = self.headers.get("Origin", ""), self.headers.get("Host", "")
        if not secrets.compare_digest(token, self.server.action_token):
            self._json(403, {"error": "Missing or invalid local action token"})
            return
        if origin and urlparse(origin).netloc != host:
            self._json(403, {"error": "Cross-origin action rejected"})
            return
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            self._json(403, {"error": "Actions are restricted to loopback clients"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 0 or length > 64000:
            self._json(413, {"error": "Action payload must be at most 64 KB"})
            return
        try:
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise ValueError("Content-Type must be application/json")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Action payload must be a JSON object")
            if is_automation:
                result = run_automation(self.repo, str(payload.get("workflow_id", "")))
                self._json(200 if result.get("status") == "passed" else 409, {"ok": result.get("status") == "passed", "result": result})
                return
            action = parsed.path.removeprefix("/api/cycle/")
            if action == "start":
                result = start_cycle(self.repo, str(payload.get("goal_id", "")), str(payload.get("title", "")))
            elif action == "evidence":
                result = attach_evidence(self.repo, str(payload.get("criterion_id", "")), str(payload.get("path", "")), str(payload.get("note", "")))
            elif action == "verify":
                result = verify_cycle(self.repo)
            elif action == "complete":
                result = complete_cycle(self.repo)
            elif action == "block":
                result = block_cycle(self.repo, str(payload.get("reason", "")))
            else:
                self._json(404, {"error": "Unknown work-cycle action"})
                return
            self._json(200, {"ok": True, "result": result})
        except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})


    def do_PUT(self) -> None:
        self._json(405, {"error": "This dashboard is read-only"})

    def do_DELETE(self) -> None:
        self._json(405, {"error": "This dashboard is read-only"})


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_dashboard(repo: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Serve the local project console. Binding beyond loopback is opt-in."""
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Dashboard only binds to loopback; remote exposure is not supported")
    root = repo.resolve()
    if not root.is_dir():
        raise ValueError(f"Repository directory does not exist: {root}")
    server = DashboardServer((host, port), DashboardHandler)
    server.repo = root  # type: ignore[attr-defined]
    server.action_token = secrets.token_urlsafe(32)  # type: ignore[attr-defined]
    actual_host, actual_port = server.server_address[:2]
    print(f"Steadfast Project Console: http://{actual_host}:{actual_port}")
    print(f"Workspace: {root}")
    print("Local task controls enabled; repository source files are never edited by the console. Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\nStopping Steadfast Project Console.")
    finally:
        server.server_close()
