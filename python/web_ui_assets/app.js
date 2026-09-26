const token = document.body.dataset.token;
    const mode = document.body.dataset.mode;
    const browseLimit = 3;
    const output = document.querySelector("#output");
    const workspace = document.querySelector("#workspace");
    let browsedConversationPages = [];
    let browsedConversationPageIndex = 0;
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
        <section class="section"><div class="section-head"><div><p class="eyebrow">Browse</p><h2>Recent conversations</h2><p class="section-note">Newest first</p></div><button class="button" data-action="browse" data-params='{"limit":3}'>Load conversations</button></div></section>`;
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

    function conversationMarkup(records) {
      return `<div class="records">${records.map(record => `<article class="record"><div><h3>${esc(record.title || record.name || "Untitled conversation")}</h3><p>${esc(record.summary || record.description || "")}</p><small>${esc(dateLabel(record.start_time || record.date))} · ID ${esc(record.id ?? record.conversation_id)}</small></div><button class="button" data-read-id="${esc(record.id ?? record.conversation_id)}">Read transcript</button></article>`).join("")}</div>`;
    }

    function renderBrowsePage(payload, pageIndex) {
      const records = conversationList(payload.data);
      let body = records.length ? conversationMarkup(records) : renderData(payload.data);
      const previous = pageIndex > 0
        ? `<button class="button" data-action="browse_previous">Previous</button>`
        : "";
      const next = payload.next_cursor != null
        ? `<button class="button" data-action="browse" data-params='${esc(JSON.stringify({ cursor: payload.next_cursor, limit: browseLimit }))}'>Next</button>`
        : "";
      if (previous || next) {
        body += `<nav class="pagination" aria-label="Conversation pages">${previous}<span>Page ${pageIndex + 1}</span>${next}</nav>`;
      }
      const extras = Object.entries(payload).filter(([key]) => !["mode", "data", "next_cursor"].includes(key));
      if (extras.length) body += `<div class="result-meta">${extras.map(([key, value]) => `${esc(key.replaceAll("_", " "))}: ${esc(typeof value === "object" ? JSON.stringify(value) : value)}`).join(" · ")}</div>`;
      output.innerHTML = `<div class="result-bar"><h2>${esc(actionTitles.browse)}</h2><span class="result-meta">${esc(payload.mode || mode)} mode</span></div>${body}`;
    }

    function renderResult(action, payload, params = {}) {
      const title = actionTitles[action] || "BeePlex result";
      let body = "";
      const records = conversationList(payload.data);
      if (action === "browse") {
        if (params.cursor) {
          browsedConversationPages = browsedConversationPages.slice(0, browsedConversationPageIndex + 1);
          browsedConversationPages.push(payload);
          browsedConversationPageIndex += 1;
        } else {
          browsedConversationPages = [payload];
          browsedConversationPageIndex = 0;
        }
        renderBrowsePage(payload, browsedConversationPageIndex);
        return;
      }
      if (action === "today") {
        const todayData = { ...(payload.data || {}) };
        delete todayData.recent_conversations;
        body = renderData(todayData);
      } else if (action === "read" && payload.data && typeof payload.data === "object") {
        const conversation = payload.data;
        const utterances = conversation.utterances || [];
        body = `<div class="result-bar"><h2>${esc(conversation.title || title)}</h2><span class="result-meta">${esc(dateLabel(conversation.start_time))}</span></div><div class="transcript">${utterances.map(turn => `<div class="utterance"><span class="speaker">${esc(turn.speaker || "Speaker")}</span><p>${esc(turn.text || "")}</p></div>`).join("")}</div>`;
        if (payload.next_offset != null) body += `<button class="button" data-action="read" data-params='${esc(JSON.stringify({ conversation_id: conversation.id, offset: payload.next_offset, limit: 50 }))}'>Load next transcript section</button>`;
      } else if (records.length) {
        body = conversationMarkup(records);
      } else {
        body = renderData(payload.data ?? payload);
      }
      const extras = Object.entries(payload).filter(([key, value]) => !["mode", "data"].includes(key) && value != null);
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
        renderResult(action, payload, params);
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
      else if (actionButton.dataset.action === "browse_previous") {
        browsedConversationPageIndex -= 1;
        renderBrowsePage(browsedConversationPages[browsedConversationPageIndex], browsedConversationPageIndex);
      }
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