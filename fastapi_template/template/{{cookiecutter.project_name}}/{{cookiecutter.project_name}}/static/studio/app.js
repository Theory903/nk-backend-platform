/* NK API Studio — OpenAPI → Postman-like console */

(() => {
  const HISTORY_KEY = "nk.studio.history";
  const MAX_HISTORY = 25;

  function loadHistory() {
    try {
      return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    } catch (_) {
      return [];
    }
  }

  const state = {
    spec: null,
    endpoints: [],
    selectedId: null,
    foldersOpen: {},
    reqTab: "params",
    resTab: "body",
    params: [],
    headers: [{ key: "Accept", value: "application/json", enabled: true }],
    body: "{\n  \n}",
    authType: localStorage.getItem("nk.authType") || "none",
    authToken: localStorage.getItem("nk.authToken") || "",
    lastResponse: null,
    history: loadHistory(),
  };

  const el = {
    collection: document.getElementById("collection"),
    history: document.getElementById("history"),
    search: document.getElementById("search"),
    method: document.getElementById("method"),
    url: document.getElementById("url"),
    send: document.getElementById("send"),
    copyCurl: document.getElementById("copy-curl"),
    paramsPane: document.getElementById("params-pane"),
    headersPane: document.getElementById("headers-pane"),
    bodyPane: document.getElementById("body-pane"),
    bodyEditor: document.getElementById("body-editor"),
    docsPane: document.getElementById("docs-pane"),
    responseMeta: document.getElementById("response-meta"),
    responseBody: document.getElementById("response-body"),
    authType: document.getElementById("auth-type"),
    authToken: document.getElementById("auth-token"),
    title: document.getElementById("app-title"),
    subtitle: document.getElementById("app-subtitle"),
  };

  function saveHistory() {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history.slice(0, MAX_HISTORY)));
  }

  function syncMethodColor() {
    const m = methodClass(el.method.value);
    el.method.className = `method-select method ${m}`;
  }

  function methodClass(m) {
    return (m || "get").toLowerCase();
  }

  function pathToTemplate(path) {
    return path.replace(/\{([^}]+)\}/g, (_, name) => `:${name}`);
  }

  function parseSpec(spec) {
    const endpoints = [];
    const paths = spec.paths || {};
    for (const [path, item] of Object.entries(paths)) {
      for (const [method, op] of Object.entries(item)) {
        if (!["get", "post", "put", "patch", "delete", "head", "options"].includes(method)) {
          continue;
        }
        const tags = (op.tags && op.tags.length ? op.tags : ["default"]);
        endpoints.push({
          id: `${method}:${path}`,
          method: method.toUpperCase(),
          path,
          summary: op.summary || op.operationId || path,
          description: op.description || "",
          tags,
          parameters: op.parameters || [],
          requestBody: op.requestBody || null,
          operation: op,
        });
      }
    }
    endpoints.sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method));
    return endpoints;
  }

  function groupByTag(endpoints, query) {
    const q = (query || "").trim().toLowerCase();
    const groups = {};
    for (const ep of endpoints) {
      const hay = `${ep.method} ${ep.path} ${ep.summary} ${ep.tags.join(" ")}`.toLowerCase();
      if (q && !hay.includes(q)) continue;
      for (const tag of ep.tags) {
        (groups[tag] ||= []).push(ep);
      }
    }
    return Object.fromEntries(Object.entries(groups).sort(([a], [b]) => a.localeCompare(b)));
  }

  function renderCollection() {
    const groups = groupByTag(state.endpoints, el.search.value);
    const tags = Object.keys(groups);
    if (!tags.length) {
      el.collection.innerHTML = `<div class="empty">No matching endpoints</div>`;
      return;
    }
    el.collection.innerHTML = tags.map((tag) => {
      const open = state.foldersOpen[tag] !== false;
      const items = groups[tag].map((ep) => {
        const active = ep.id === state.selectedId ? "active" : "";
        return `<button class="endpoint ${active}" data-id="${ep.id}" title="${ep.summary}">
          <span class="method ${methodClass(ep.method)}">${ep.method}</span>
          <span class="ep-path">${ep.path}</span>
          <span class="ep-summary">${escapeHtml(ep.summary)}</span>
        </button>`;
      }).join("");
      return `<div class="folder">
        <button class="folder-title" data-folder="${escapeHtml(tag)}">
          <span class="chev">${open ? "▾" : "▸"}</span>
          <span>${escapeHtml(tag)}</span>
          <span class="count">${groups[tag].length}</span>
        </button>
        <div class="folder-body" style="display:${open ? "block" : "none"}">${items}</div>
      </div>`;
    }).join("");
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function selectEndpoint(id) {
    const ep = state.endpoints.find((e) => e.id === id);
    if (!ep) return;
    state.selectedId = id;
    el.method.value = ep.method;
    syncMethodColor();
    el.url.value = window.location.origin + ep.path;

    const queryParams = (ep.parameters || []).filter((p) => p.in === "query");
    const pathParams = (ep.parameters || []).filter((p) => p.in === "path");
    const headerParams = (ep.parameters || []).filter((p) => p.in === "header");

    state.params = [
      ...pathParams.map((p) => ({
        key: p.name,
        value: p.schema?.default != null ? String(p.schema.default) : "",
        enabled: true,
        kind: "path",
        required: !!p.required,
      })),
      ...queryParams.map((p) => ({
        key: p.name,
        value: p.schema?.default != null ? String(p.schema.default) : "",
        enabled: true,
        kind: "query",
        required: !!p.required,
      })),
    ];
    if (!state.params.length) {
      state.params = [{ key: "", value: "", enabled: true, kind: "query", required: false }];
    }

    const baseHeaders = [
      { key: "Accept", value: "application/json", enabled: true },
      { key: "Content-Type", value: "application/json", enabled: ["POST", "PUT", "PATCH"].includes(ep.method) },
    ];
    state.headers = [
      ...baseHeaders,
      ...headerParams.map((p) => ({
        key: p.name,
        value: "",
        enabled: !!p.required,
      })),
    ];

    const example = extractExample(ep.requestBody);
    state.body = example || "{\n  \n}";
    el.bodyEditor.value = state.body;

    el.docsPane.innerHTML = `
      <p class="desc"><strong>${escapeHtml(ep.summary)}</strong></p>
      <p class="desc">${escapeHtml(ep.description || "No description.")}</p>
      <p class="desc">Operation: <span class="code-inline">${escapeHtml(ep.id)}</span></p>
    `;

    setReqTab(state.reqTab);
    renderCollection();
    renderKvTables();
  }

  function extractExample(requestBody) {
    if (!requestBody || !requestBody.content) return null;
    const json = requestBody.content["application/json"];
    if (!json) return null;
    if (json.example) return JSON.stringify(json.example, null, 2);
    if (json.examples) {
      const first = Object.values(json.examples)[0];
      if (first?.value) return JSON.stringify(first.value, null, 2);
    }
    if (json.schema?.example) return JSON.stringify(json.schema.example, null, 2);
    return null;
  }

  function renderKvTables() {
    el.paramsPane.innerHTML = kvTableHtml("params", state.params, true);
    el.headersPane.innerHTML = kvTableHtml("headers", state.headers, false);
    bindKvHandlers();
  }

  function kvTableHtml(kind, rows, showKind) {
    const body = rows.map((row, idx) => `
      <tr>
        <td style="width:36px"><input type="checkbox" data-kind="${kind}" data-idx="${idx}" data-field="enabled" ${row.enabled ? "checked" : ""}/></td>
        <td><input data-kind="${kind}" data-idx="${idx}" data-field="key" value="${escapeHtml(row.key)}" placeholder="Key"/></td>
        <td><input data-kind="${kind}" data-idx="${idx}" data-field="value" value="${escapeHtml(row.value)}" placeholder="Value"/></td>
        ${showKind ? `<td style="width:70px;color:var(--muted);font-size:.72rem">${row.kind || ""}</td>` : ""}
      </tr>
    `).join("");
    return `
      <table class="kv-table">
        <thead><tr><th></th><th>Key</th><th>Value</th>${showKind ? "<th>In</th>" : ""}</tr></thead>
        <tbody>${body}</tbody>
      </table>
      <div class="kv-actions">
        <button class="chip" data-add="${kind}">Add row</button>
      </div>
    `;
  }

  function bindKvHandlers() {
    el.paramsPane.querySelectorAll("input").forEach((input) => {
      input.addEventListener("change", onKvChange);
      input.addEventListener("input", onKvChange);
    });
    el.headersPane.querySelectorAll("input").forEach((input) => {
      input.addEventListener("change", onKvChange);
      input.addEventListener("input", onKvChange);
    });
    el.paramsPane.querySelector("[data-add='params']")?.addEventListener("click", () => {
      state.params.push({ key: "", value: "", enabled: true, kind: "query", required: false });
      renderKvTables();
    });
    el.headersPane.querySelector("[data-add='headers']")?.addEventListener("click", () => {
      state.headers.push({ key: "", value: "", enabled: true });
      renderKvTables();
    });
  }

  function onKvChange(ev) {
    const t = ev.target;
    const kind = t.dataset.kind;
    const idx = Number(t.dataset.idx);
    const field = t.dataset.field;
    const list = kind === "params" ? state.params : state.headers;
    if (!list[idx]) return;
    list[idx][field] = field === "enabled" ? t.checked : t.value;
  }

  function setReqTab(name) {
    state.reqTab = name;
    document.querySelectorAll("[data-req-tab]").forEach((b) => {
      b.classList.toggle("active", b.dataset.reqTab === name);
    });
    el.paramsPane.hidden = name !== "params";
    el.headersPane.hidden = name !== "headers";
    el.bodyPane.hidden = name !== "body";
    el.docsPane.hidden = name !== "docs";
  }

  function setResTab(name) {
    state.resTab = name;
    document.querySelectorAll("[data-res-tab]").forEach((b) => {
      b.classList.toggle("active", b.dataset.resTab === name);
    });
  }

  function buildUrl() {
    let url = el.url.value.trim();
    const pathParams = state.params.filter((p) => p.enabled && p.kind === "path" && p.key);
    for (const p of pathParams) {
      url = url.replace(`{${p.key}}`, encodeURIComponent(p.value));
      url = url.replace(`:${p.key}`, encodeURIComponent(p.value));
    }
    const u = new URL(url, window.location.origin);
    for (const p of state.params.filter((x) => x.enabled && x.kind === "query" && x.key)) {
      u.searchParams.set(p.key, p.value);
    }
    return u.toString();
  }

  function buildHeaders() {
    const headers = {};
    for (const h of state.headers.filter((x) => x.enabled && x.key)) {
      headers[h.key] = h.value;
    }
    if (state.authType === "bearer" && state.authToken) {
      headers.Authorization = `Bearer ${state.authToken}`;
    } else if (state.authType === "apiKey" && state.authToken) {
      headers["X-API-Key"] = state.authToken;
    }
    return headers;
  }

  function buildCurl() {
    const method = el.method.value.toUpperCase();
    const url = buildUrl();
    const headers = buildHeaders();
    const parts = [`curl -X ${method} '${url}'`];
    for (const [k, v] of Object.entries(headers)) {
      parts.push(`  -H '${k}: ${String(v).replace(/'/g, "'\\''")}'`);
    }
    if (!["GET", "HEAD"].includes(method) && el.bodyEditor.value.trim()) {
      const body = el.bodyEditor.value.replace(/'/g, "'\\''");
      parts.push(`  -d '${body}'`);
    }
    return parts.join(" \\\n");
  }

  async function copyCurl() {
    try {
      await navigator.clipboard.writeText(buildCurl());
      el.copyCurl.textContent = "Copied!";
      setTimeout(() => {
        el.copyCurl.textContent = "Copy cURL";
      }, 1200);
    } catch (_) {
      el.copyCurl.textContent = "Copy failed";
      setTimeout(() => {
        el.copyCurl.textContent = "Copy cURL";
      }, 1200);
    }
  }

  function pushHistory(entry) {
    state.history = [entry, ...state.history.filter((h) => !(h.method === entry.method && h.url === entry.url))].slice(0, MAX_HISTORY);
    saveHistory();
    renderHistory();
  }

  function renderHistory() {
    if (!el.history) return;
    if (!state.history.length) {
      el.history.innerHTML = `<div class="empty" style="padding:.75rem">No requests yet</div>`;
      return;
    }
    el.history.innerHTML = state.history.map((h, idx) => `
      <button type="button" class="hist-item" data-hist="${idx}" title="${escapeHtml(h.url)}">
        <span class="method ${methodClass(h.method)}">${h.method}</span>
        <span class="ep-path">${escapeHtml(h.path || h.url)}</span>
        <span class="pill ${h.ok ? "ok" : "err"}" style="margin-left:auto">${h.status || "ERR"}</span>
      </button>
    `).join("");
  }

  async function sendRequest() {
    const method = el.method.value.toUpperCase();
    const url = buildUrl();
    const headers = buildHeaders();
    const init = { method, headers };
    if (!["GET", "HEAD"].includes(method)) {
      init.body = el.bodyEditor.value;
    }
    el.send.disabled = true;
    el.send.textContent = "Sending…";
    const started = performance.now();
    try {
      const res = await fetch(url, init);
      const elapsed = Math.round(performance.now() - started);
      const text = await res.text();
      let pretty = text;
      try {
        pretty = JSON.stringify(JSON.parse(text), null, 2);
      } catch (_) {
        /* keep raw */
      }
      state.lastResponse = {
        status: res.status,
        statusText: res.statusText,
        elapsed,
        headers: [...res.headers.entries()],
        body: pretty,
        ok: res.ok,
      };
      pushHistory({
        method,
        url,
        path: new URL(url).pathname + new URL(url).search,
        status: res.status,
        ok: res.ok,
        body: el.bodyEditor.value,
        at: Date.now(),
      });
      renderResponse();
    } catch (err) {
      state.lastResponse = {
        status: 0,
        statusText: "Network Error",
        elapsed: Math.round(performance.now() - started),
        headers: [],
        body: String(err),
        ok: false,
      };
      pushHistory({
        method,
        url,
        path: url,
        status: 0,
        ok: false,
        body: el.bodyEditor.value,
        at: Date.now(),
      });
      renderResponse();
    } finally {
      el.send.disabled = false;
      el.send.textContent = "Send";
    }
  }

  function renderResponse() {
    const r = state.lastResponse;
    if (!r) {
      el.responseMeta.innerHTML = "";
      el.responseBody.value = "";
      return;
    }
    const statusClass = r.status === 0 ? "err" : r.ok ? "ok" : r.status >= 400 ? "err" : "warn";
    el.responseMeta.innerHTML = `
      <span class="pill ${statusClass}">${r.status || "ERR"} ${escapeHtml(r.statusText)}</span>
      <span class="pill">${r.elapsed} ms</span>
      <span class="pill">${r.body ? new Blob([r.body]).size : 0} B</span>
    `;
    if (state.resTab === "headers") {
      el.responseBody.value = r.headers.map(([k, v]) => `${k}: ${v}`).join("\n") || "(no headers)";
    } else {
      el.responseBody.value = r.body || "";
    }
  }

  async function boot() {
    const openapiUrl = document.body.dataset.openapi || "/api/openapi.json";
    const res = await fetch(openapiUrl);
    state.spec = await res.json();
    state.endpoints = parseSpec(state.spec);
    el.title.textContent = state.spec.info?.title || "API Studio";
    el.subtitle.textContent = state.spec.info?.version
      ? `v${state.spec.info.version}`
      : "OpenAPI console";

    for (const tag of new Set(state.endpoints.flatMap((e) => e.tags))) {
      if (state.foldersOpen[tag] === undefined) state.foldersOpen[tag] = true;
    }

    el.authType.value = state.authType;
    el.authToken.value = state.authToken;
    renderCollection();
    renderHistory();
    renderKvTables();
    syncMethodColor();

    if (state.endpoints[0]) selectEndpoint(state.endpoints[0].id);

    el.search.addEventListener("input", renderCollection);
    el.collection.addEventListener("click", (ev) => {
      const folder = ev.target.closest("[data-folder]");
      if (folder) {
        const name = folder.dataset.folder;
        state.foldersOpen[name] = !(state.foldersOpen[name] !== false);
        renderCollection();
        return;
      }
      const epBtn = ev.target.closest(".endpoint");
      if (epBtn) selectEndpoint(epBtn.dataset.id);
    });
    el.history?.addEventListener("click", (ev) => {
      const item = ev.target.closest("[data-hist]");
      if (!item) return;
      const h = state.history[Number(item.dataset.hist)];
      if (!h) return;
      el.method.value = h.method;
      syncMethodColor();
      el.url.value = h.url;
      if (h.body != null) {
        el.bodyEditor.value = h.body;
        state.body = h.body;
      }
    });
    document.querySelectorAll("[data-req-tab]").forEach((b) => {
      b.addEventListener("click", () => setReqTab(b.dataset.reqTab));
    });
    document.querySelectorAll("[data-res-tab]").forEach((b) => {
      b.addEventListener("click", () => {
        setResTab(b.dataset.resTab);
        renderResponse();
      });
    });
    el.send.addEventListener("click", sendRequest);
    el.copyCurl?.addEventListener("click", copyCurl);
    el.method.addEventListener("change", syncMethodColor);
    el.bodyEditor.addEventListener("input", () => {
      state.body = el.bodyEditor.value;
    });
    el.authType.addEventListener("change", () => {
      state.authType = el.authType.value;
      localStorage.setItem("nk.authType", state.authType);
    });
    el.authToken.addEventListener("input", () => {
      state.authToken = el.authToken.value;
      localStorage.setItem("nk.authToken", state.authToken);
    });
    window.addEventListener("keydown", (ev) => {
      if ((ev.metaKey || ev.ctrlKey) && ev.key === "Enter") {
        ev.preventDefault();
        sendRequest();
      }
    });
  }

  boot().catch((err) => {
    el.collection.innerHTML = `<div class="empty">Failed to load OpenAPI: ${escapeHtml(err)}</div>`;
  });
})();
