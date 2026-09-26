"""Local button-driven interface for BeePlex."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
import secrets
import webbrowser


PAGE = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>BeePlex | Memory desk</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #20352f;
      --muted: #67766f;
      --paper: #f4f7f4;
      --white: #fff;
      --line: #dce5df;
      --green: #176a52;
      --green-dark: #104c3b;
      --green-pale: #e5f0ea;
      --gold: #dbad3a;
      --red: #a4483e;
      --shadow: 0 12px 34px rgba(31, 61, 49, .07);
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.5 "Segoe UI", "Aptos", sans-serif; }
    button, input, select { font: inherit; }
    button { cursor: pointer; }
    .shell { min-height: 100vh; display: grid; grid-template-columns: 238px minmax(0, 1fr); }
    .rail { background: var(--green-dark); color: #f6fbf7; padding: 25px 16px 18px; display: flex; flex-direction: column; gap: 32px; }
    .brand { display: flex; align-items: center; gap: 11px; padding: 0 10px; }
    .brand-mark { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid rgba(255,255,255,.55); border-radius: 8px; color: #f4ca5e; font: 700 19px Georgia, serif; }
    .brand-name { font: 700 18px Georgia, serif; letter-spacing: 0; }
    .rail-label { margin: 0 10px 9px; color: #a7c4b7; font-size: 10px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; }
    .nav { display: grid; gap: 5px; }
    .nav button { display: flex; align-items: center; gap: 11px; width: 100%; border: 0; border-radius: 6px; padding: 10px 11px; background: transparent; color: #d8e8df; text-align: left; }
    .nav button:hover { background: rgba(255,255,255,.09); color: #fff; }
    .nav button[aria-current="page"] { background: #f5f8f4; color: var(--green-dark); font-weight: 650; }
    .nav-index { width: 19px; color: var(--gold); font-size: 11px; font-weight: 700; }
    .rail-foot { margin-top: auto; padding: 13px 10px 0; border-top: 1px solid rgba(255,255,255,.17); color: #c2d8cd; font-size: 12px; }
    .main { min-width: 0; padding: 0 42px 52px; }
    .topbar { height: 66px; display: flex; align-items: center; justify-content: flex-end; gap: 12px; border-bottom: 1px solid var(--line); }
    .mode { color: var(--muted); font-size: 12px; }
    .mode strong { color: var(--green-dark); font-weight: 700; }
    .page { max-width: 1040px; margin: 0 auto; }
    .page-head { display: flex; justify-content: space-between; align-items: end; gap: 20px; padding: 34px 0 24px; border-bottom: 1px solid var(--line); }
    h1 { margin: 0; font: 400 34px/1.15 Georgia, "Times New Roman", serif; letter-spacing: 0; }
    .subhead { margin: 8px 0 0; color: var(--muted); }
    h2 { margin: 0 0 5px; font: 400 23px/1.25 Georgia, "Times New Roman", serif; letter-spacing: 0; }
    h3 { margin: 0; font-size: 15px; font-weight: 650; }
    .eyebrow { color: var(--green); font-size: 10px; font-weight: 750; letter-spacing: 1.3px; text-transform: uppercase; }
    .button { min-height: 40px; border: 1px solid var(--line); border-radius: 6px; padding: 8px 13px; background: var(--white); color: var(--ink); font-weight: 650; }
    .button:hover { border-color: #8cae9c; background: #f9fcfa; }
    .button.primary { border-color: var(--green); background: var(--green); color: white; }
    .button.primary:hover { border-color: var(--green-dark); background: var(--green-dark); }
    .button.quiet { border-color: transparent; background: transparent; color: var(--green-dark); }
    .button.danger { color: var(--red); }
    .button:focus-visible, input:focus-visible, select:focus-visible { outline: 3px solid rgba(219,173,58,.55); outline-offset: 2px; }
    .section { padding: 25px 0; border-bottom: 1px solid var(--line); }
    .section-head { display: flex; justify-content: space-between; align-items: end; gap: 15px; margin-bottom: 17px; }
    .section-note { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
    .quick-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid var(--line); border-radius: 7px; background: var(--white); box-shadow: var(--shadow); }
    .quick { min-height: 118px; display: flex; flex-direction: column; align-items: flex-start; justify-content: space-between; gap: 15px; border: 0; border-right: 1px solid var(--line); padding: 17px; background: transparent; color: var(--ink); text-align: left; }
    .quick:last-child { border-right: 0; }
    .quick:hover { background: #f7faf7; }
    .quick strong { font-size: 16px; }
    .quick span { color: var(--muted); font-size: 12px; }
    .quick .arrow { color: var(--green); font-size: 19px; line-height: 1; }
    .action-list { display: grid; border-top: 1px solid var(--line); }
    .action-row { display: flex; justify-content: space-between; align-items: center; gap: 20px; padding: 15px 0; border-bottom: 1px solid var(--line); }
    .action-row p { margin: 3px 0 0; color: var(--muted); font-size: 13px; }
    .form-row { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; }
    .field { display: grid; flex: 1 1 180px; gap: 5px; }
    .field label { color: var(--muted); font-size: 12px; font-weight: 650; }
    input[type="text"], input[type="date"] { min-height: 41px; width: 100%; border: 1px solid #cbd8d0; border-radius: 5px; padding: 8px 10px; background: white; color: var(--ink); }
    .check-field { display: flex; align-items: center; gap: 8px; min-height: 41px; color: var(--muted); font-size: 13px; }
    .check-field input { accent-color: var(--green); width: 16px; height: 16px; }
    .result { padding: 23px 0; }
    .result:empty { display: none; }
    .result-bar { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
    .result-bar h2 { margin: 0; font-size: 20px; }
    .result-meta { color: var(--muted); font-size: 12px; }
    .message { margin: 18px 0; color: var(--muted); }
    .message.error { color: var(--red); }
    .records { display: grid; }
    .record { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 14px; padding: 14px 2px; border-bottom: 1px solid var(--line); }
    .record p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
    .record small { display: block; margin-top: 6px; color: #7b8982; font-size: 11px; }
    .transcript { display: grid; gap: 0; margin-top: 15px; }
    .utterance { display: grid; grid-template-columns: 120px minmax(0,1fr); gap: 18px; padding: 13px 0; border-bottom: 1px solid var(--line); }
    .speaker { color: var(--green-dark); font-size: 12px; font-weight: 700; }
    .utterance p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
    .data-list { display: grid; }
    .data-entry { padding: 12px 0; border-bottom: 1px solid var(--line); }
    .data-entry > strong { color: var(--green-dark); font-size: 12px; }
    .data-entry p { margin: 5px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }
    .data-entry .data-entry { margin-left: 15px; border-bottom: 0; border-left: 2px solid var(--line); padding: 7px 0 7px 12px; }
    .loading { display: inline-flex; align-items: center; gap: 9px; color: var(--muted); }
    .loading::before { width: 8px; height: 8px; border-radius: 50%; background: var(--gold); content: ""; animation: pulse 1s ease-in-out infinite alternate; }
    @keyframes pulse { to { opacity: .35; transform: scale(.75); } }
    .empty { padding: 28px 0; color: var(--muted); }
    @media (max-width: 800px) {
      .shell { grid-template-columns: minmax(0, 1fr); }
      .rail { gap: 15px; padding: 13px 16px 10px; }
      .brand { padding: 0 2px; }
      .rail nav { min-width: 0; max-width: 100%; overflow-x: auto; }
      .rail-label, .rail-foot { display: none; }
      .nav { display: flex; width: max-content; }
      .nav button { width: auto; white-space: nowrap; padding: 9px 10px; }
      .nav-index { display: none; }
      .main { padding: 0 20px 35px; }
      .topbar { height: 52px; }
      .page-head { padding-top: 25px; }
    }
    @media (max-width: 560px) {
      .main { padding-right: 15px; padding-left: 15px; }
      .page-head { align-items: flex-start; flex-direction: column; }
      h1 { font-size: 30px; }
      .quick-grid { grid-template-columns: 1fr; }
      .quick { min-height: 84px; flex-direction: row; align-items: center; border-right: 0; border-bottom: 1px solid var(--line); }
      .quick:last-child { border-bottom: 0; }
      .quick span { margin-left: auto; }
      .record { grid-template-columns: 1fr; }
      .record .button { justify-self: start; }
      .utterance { grid-template-columns: 1fr; gap: 4px; }
      .action-row { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="rail">
      <div class="brand"><div class="brand-mark">B</div><div class="brand-name">BeePlex</div></div>
      <nav aria-label="Main navigation">
        <p class="rail-label">Memory desk</p>
        <div class="nav">
          <button data-page="home" aria-current="page"><span class="nav-index">01</span>Overview</button>
          <button data-page="conversations"><span class="nav-index">02</span>Conversations</button>
          <button data-page="commitments"><span class="nav-index">03</span>Commitments</button>
          <button data-page="reflection"><span class="nav-index">04</span>Reflection</button>
          <button data-page="files"><span class="nav-index">05</span>Journal &amp; files</button>
        </div>
      </nav>
      <div class="rail-foot">Local on this computer<br><span id="railMode">Checking mode</span></div>
    </aside>
    <main class="main">
      <div class="topbar">
        <span class="mode">Mode: <strong id="modeLabel">__MODE__</strong></span>
        <button class="button quiet" data-action="status">Check connection</button>
      </div>
      <div class="page">
        <header class="page-head">
          <div><p class="eyebrow" id="pageEyebrow">Bee memory</p><h1 id="pageTitle">Overview</h1><p class="subhead" id="pageSubhead">Recent conversations, ready when you are.</p></div>
        </header>
        <div id="workspace"></div>
        <section id="output" class="result" aria-live="polite"></section>
      </div>
    </main>
  </div>
  <script>
    const token = "__TOKEN__";
    const mode = "__MODE__";
    const output = document.querySelector("#output");
    const workspace = document.querySelector("#workspace");
    const pageInfo = {
      home: ["Bee memory", "Overview", "Recent conversations, ready when you are."],
      conversations: ["Explore", "Conversations", "Search a topic or open a recent transcript."],
      commitments: ["Keep track", "Commitments", "Your open tasks and follow-ups."],
      reflection: ["Look back", "Reflection", "Conversation patterns, treated as signals rather than judgments."],
      files: ["Your records", "Journal & files", "Read your profile or create local exports."],
    };
    const actionTitles = {
      status: "Connection check", context: "Recent context", today: "Today's context",
      search: "Search results", browse: "Recent conversations", read: "Transcript",
      todos: "Commitments", score: "Conversation scores", disagreements: "BeePlex comparison",
      profile: "Saved profile", refresh_profile: "Profile updated", diary: "Diary written", report: "Report created",
    };
    document.querySelector("#railMode").textContent = mode === "demo" ? "Sample memories" : "Bee account";

    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
    }

    function dateLabel(value) {
      if (value == null || value === "") return "";
      const numeric = typeof value === "number" ? value : Number(value);
      const date = Number.isFinite(numeric) && numeric > 100000000000
        ? new Date(numeric)
        : new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
    }

    function homeMarkup() {
      return `<section class="section"><div class="section-head"><div><p class="eyebrow">Start here</p><h2>What would you like to find?</h2></div></div>
        <div class="quick-grid">
          <button class="quick" data-action="context" data-params='{"period":"recent","limit":10}'><strong>Catch up</strong><span>Recent conversations</span><b class="arrow">&#8594;</b></button>
          <button class="quick" data-action="today"><strong>Today's overview</strong><span>Daily summary</span><b class="arrow">&#8594;</b></button>
          <button class="quick" data-page="conversations"><strong>Find a conversation</strong><span>Search or browse</span><b class="arrow">&#8594;</b></button>
        </div></section>
        <section class="section"><div class="section-head"><div><p class="eyebrow">More to explore</p><h2>Your memory, in context</h2></div></div>
        <div class="action-list">
          <div class="action-row"><div><h3>Commitments</h3><p>Review tasks and follow-ups.</p></div><button class="button" data-page="commitments">Open commitments</button></div>
          <div class="action-row"><div><h3>Reflection</h3><p>See conversation signals and areas worth a closer look.</p></div><button class="button" data-page="reflection">Open reflection</button></div>
          <div class="action-row"><div><h3>Journal and files</h3><p>Read your saved profile or create a local export.</p></div><button class="button" data-page="files">Open records</button></div>
        </div></section>`;
    }

    function pageMarkup(page) {
      if (page === "home") return homeMarkup();
      if (page === "conversations") return `<section class="section"><div class="section-head"><div><p class="eyebrow">Find a memory</p><h2>Search conversations</h2></div></div>
        <form id="searchForm"><div class="form-row"><div class="field"><label for="query">Topic or phrase</label><input id="query" name="query" type="text" maxlength="1000" placeholder="For example, launch plans" required></div>
        <div class="field"><label for="since">From</label><input id="since" name="since" type="date"></div><div class="field"><label for="until">Through</label><input id="until" name="until" type="date"></div>
        <label class="check-field"><input name="semantic" type="checkbox"> Search by meaning</label><button class="button primary" type="submit">Search</button></div></form></section>
        <section class="section"><div class="section-head"><div><p class="eyebrow">Browse</p><h2>Recent conversations</h2><p class="section-note">Newest first</p></div><button class="button" data-action="browse">Load conversations</button></div></section>`;
      if (page === "commitments") return `<section class="section"><div class="section-head"><div><p class="eyebrow">Your list</p><h2>Open commitments</h2><p class="section-note">BeePlex reads these from Bee; it does not change them.</p></div><button class="button primary" data-action="todos">Load commitments</button></div></section>`;
      if (page === "reflection") return `<section class="section"><div class="section-head"><div><p class="eyebrow">Recent patterns</p><h2>Conversation signals</h2><p class="section-note">Heuristic observations, not objective judgments.</p></div><button class="button primary" data-action="score">Score recent conversations</button></div>
        <div class="action-row"><div><h3>Compare perspectives</h3><p>Line up Bee's summaries with transcript-based signals.</p></div><button class="button" data-action="disagreements">Compare</button></div></section>`;
      return `<section class="section"><div class="section-head"><div><p class="eyebrow">Read and create</p><h2>Saved records</h2></div></div>
        <div class="action-list">
          <div class="action-row"><div><h3>Profile</h3><p>Read your saved profile. Refreshing it uses recent conversations.</p></div><div><button class="button" data-action="profile">Read profile</button> <button class="button" data-action="refresh_profile" data-confirm="Refresh your saved profile using Bee conversation data?">Refresh profile</button></div></div>
          <div class="action-row"><div><h3>Diary</h3><p>Write today's diary to your local BeePlex data folder.</p></div><button class="button" data-action="diary" data-confirm="Write or replace today's diary entry?">Write diary</button></div>
          <div class="action-row"><div><h3>Office report</h3><p>Create Word, Excel, PowerPoint, and dashboard files locally.</p></div><button class="button primary" data-action="report" data-confirm="Generate report files for recent conversations? Existing files for the same date may be replaced.">Create report</button></div>
        </div></section>`;
    }

    function showPage(page) {
      const info = pageInfo[page] || pageInfo.home;
      document.querySelector("#pageEyebrow").textContent = info[0];
      document.querySelector("#pageTitle").textContent = info[1];
      document.querySelector("#pageSubhead").textContent = info[2];
      workspace.innerHTML = pageMarkup(page);
      document.querySelectorAll(".nav [data-page]").forEach(button => {
        button.setAttribute("aria-current", button.dataset.page === page ? "page" : "false");
      });
      output.innerHTML = "";
    }

    function conversationList(value) {
      const found = [];
      const seen = new Set();
      function visit(item) {
        if (Array.isArray(item)) return item.forEach(visit);
        if (!item || typeof item !== "object") return;
        const id = item.id ?? item.conversation_id;
        const title = item.title ?? item.name;
        if (id && title && !seen.has(String(id))) {
          seen.add(String(id)); found.push(item); return;
        }
        Object.values(item).forEach(visit);
      }
      visit(value);
      return found;
    }

    function renderData(value) {
      if (value == null) return `<p class="empty">No saved information found.</p>`;
      if (typeof value === "string") return `<p class="data-entry">${esc(value)}</p>`;
      if (Array.isArray(value)) {
        if (!value.length) return `<p class="empty">Nothing to show.</p>`;
        return `<div class="data-list">${value.map(item => `<div class="data-entry">${renderData(item)}</div>`).join("")}</div>`;
      }
      if (typeof value === "object") {
        return `<div class="data-list">${Object.entries(value).filter(([, item]) => item != null).map(([key, item]) => `<div class="data-entry"><strong>${esc(key.replaceAll("_", " "))}</strong>${typeof item === "object" ? renderData(item) : `<p>${esc(item)}</p>`}</div>`).join("")}</div>`;
      }
      return `<p class="data-entry">${esc(value)}</p>`;
    }

    function renderResult(action, payload) {
      const title = actionTitles[action] || "BeePlex result";
      let body = "";
      const records = conversationList(payload.data);
      if (action === "read" && payload.data && typeof payload.data === "object") {
        const conversation = payload.data;
        const utterances = conversation.utterances || [];
        body = `<div class="result-bar"><h2>${esc(conversation.title || title)}</h2><span class="result-meta">${esc(dateLabel(conversation.start_time))}</span></div><div class="transcript">${utterances.map(turn => `<div class="utterance"><span class="speaker">${esc(turn.speaker || "Speaker")}</span><p>${esc(turn.text || "")}</p></div>`).join("")}</div>`;
        if (payload.next_offset != null) body += `<button class="button" data-action="read" data-params='${esc(JSON.stringify({ conversation_id: conversation.id, offset: payload.next_offset, limit: 50 }))}'>Load next transcript section</button>`;
      } else if (records.length) {
        body = `<div class="records">${records.map(record => `<article class="record"><div><h3>${esc(record.title || record.name || "Untitled conversation")}</h3><p>${esc(record.summary || record.description || "")}</p><small>${esc(dateLabel(record.start_time || record.date))} · ID ${esc(record.id ?? record.conversation_id)}</small></div><button class="button" data-read-id="${esc(record.id ?? record.conversation_id)}">Read transcript</button></article>`).join("")}</div>`;
      } else {
        body = renderData(payload.data ?? payload);
      }
      const extras = Object.entries(payload).filter(([key]) => !["mode", "data"].includes(key));
      if (extras.length) body += `<div class="result-meta">${extras.map(([key, value]) => `${esc(key.replaceAll("_", " "))}: ${esc(typeof value === "object" ? JSON.stringify(value) : value)}`).join(" · ")}</div>`;
      output.innerHTML = `<div class="result-bar"><h2>${esc(title)}</h2><span class="result-meta">${esc(payload.mode || mode)} mode</span></div>${body}`;
    }

    async function runAction(action, params = {}) {
      output.innerHTML = `<p class="loading">Loading ${esc(actionTitles[action] || "BeePlex data")}...</p>`;
      try {
        const response = await fetch("/api/action", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-BeePlex-Token": token },
          body: JSON.stringify({ action, params }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "The request could not be completed.");
        renderResult(action, payload);
      } catch (error) {
        output.innerHTML = `<p class="message error">${esc(error.message || "BeePlex could not complete that request.")}</p>`;
      }
    }

    document.addEventListener("click", event => {
      const pageButton = event.target.closest("[data-page]");
      if (pageButton) { showPage(pageButton.dataset.page); return; }
      const readButton = event.target.closest("[data-read-id]");
      if (readButton) { runAction("read", { conversation_id: readButton.dataset.readId }); return; }
      const actionButton = event.target.closest("[data-action]");
      if (!actionButton) return;
      if (actionButton.dataset.confirm && !window.confirm(actionButton.dataset.confirm)) return;
      let params = {};
      try { params = JSON.parse(actionButton.dataset.params || "{}"); } catch { params = {}; }
      if (actionButton.dataset.action === "today") runAction("today", { period: "today" });
      else if (actionButton.dataset.action === "refresh_profile") runAction("refresh_profile", { refresh: true });
      else runAction(actionButton.dataset.action, params);
    });

    document.addEventListener("submit", event => {
      if (event.target.id !== "searchForm") return;
      event.preventDefault();
      const form = new FormData(event.target);
      const params = { query: form.get("query"), limit: 10, semantic: form.has("semantic") };
      if (form.get("since")) params.since = form.get("since");
      if (form.get("until")) params.until = form.get("until");
      runAction("search", params);
    });

    showPage("home");
  </script>
</body>
</html>'''


ACTION_FUNCTIONS = {
    "status": "connection_status",
    "context": "get_context",
    "today": "get_context",
    "search": "search_memories",
    "browse": "fetch_conversations",
    "read": "read_conversation",
    "todos": "get_todos",
    "score": "score_conversations",
    "disagreements": "disagreement_view",
    "report": "generate_report",
    "diary": "bee_diary",
    "profile": "user_profile",
    "refresh_profile": "user_profile",
}


def perform_action(action, params):
    if action not in ACTION_FUNCTIONS:
        raise ValueError("Unknown BeePlex action.")
    if not isinstance(params, dict):
        raise ValueError("Action parameters must be an object.")

    from pydantic import validate_call

    from . import server

    function = getattr(server, ACTION_FUNCTIONS[action])
    return validate_call(function)(**params)


class LocalHTTPServer(HTTPServer):
    def __init__(self, address, token):
        super().__init__(address, RequestHandler)
        self.ui_token = token


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "BeePlexLocal/1.0"

    def log_message(self, format, *args):
        return

    def _send(self, status, body, content_type):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def _json(self, status, payload):
        self._send(
            status,
            json.dumps(payload, ensure_ascii=True),
            "application/json; charset=utf-8",
        )

    def _is_local_request(self):
        host = self.headers.get("Host", "").split(":", 1)[0].strip("[]").lower()
        return self.client_address[0] in {"127.0.0.1", "::1"} and host in {
            "127.0.0.1",
            "localhost",
        }

    def do_GET(self):
        if not self._is_local_request():
            self._send(403, "Local access only.", "text/plain; charset=utf-8")
            return
        if self.path != "/":
            self._send(404, "Not found.", "text/plain; charset=utf-8")
            return

        from .config import DEMO

        mode = "demo" if DEMO else "live"
        page = PAGE.replace("__TOKEN__", self.server.ui_token).replace("__MODE__", mode)
        self._send(200, page, "text/html; charset=utf-8")

    def do_POST(self):
        if not self._is_local_request():
            self._json(403, {"error": "Local access only."})
            return
        if self.path != "/api/action":
            self._json(404, {"error": "Not found."})
            return
        supplied_token = self.headers.get("X-BeePlex-Token", "")
        if not hmac.compare_digest(supplied_token, self.server.ui_token):
            self._json(403, {"error": "This page is no longer authorized. Reload it and try again."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 65536:
                raise ValueError("Invalid request size.")
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict):
                raise ValueError("Request must be a JSON object.")
            result = perform_action(request.get("action"), request.get("params", {}))
        except Exception as exc:
            from pydantic import ValidationError

            from .client import BeeError

            status = 400 if isinstance(exc, (ValueError, ValidationError, BeeError)) else 500
            message = str(exc) if status == 400 else "BeePlex could not complete that action."
            self._json(status, {"error": message})
            return
        self._json(200, result)


def serve(port=8765, open_browser=True):
    token = secrets.token_urlsafe(32)
    try:
        httpd = LocalHTTPServer(("127.0.0.1", port), token)
    except OSError:
        httpd = LocalHTTPServer(("127.0.0.1", 0), token)
    address, active_port = httpd.server_address
    url = f"http://{address}:{active_port}/"
    print(f"BeePlex local interface: {url}")
    print("Press Ctrl+C to stop the interface.")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBeePlex interface stopped.")
    finally:
        httpd.server_close()