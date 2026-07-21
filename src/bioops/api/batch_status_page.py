from __future__ import annotations


BATCH_STATUS_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Batch Status | BioOps</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7f8fa;
      color: #20242b;
    }

    * {
      box-sizing: border-box;
    }

    body {
      min-width: 320px;
      margin: 0;
      background: #f7f8fa;
    }

    .visually-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }

    a {
      color: inherit;
    }

    button,
    input,
    select {
      font: inherit;
    }

    button,
    .button-link {
      min-height: 38px;
      border: 1px solid #c9ced7;
      border-radius: 6px;
      background: #ffffff;
      color: #20242b;
      cursor: pointer;
      font-weight: 650;
    }

    button:hover,
    .button-link:hover {
      border-color: #3468c0;
      background: #f2f6fc;
    }

    button:focus-visible,
    a:focus-visible,
    input:focus-visible,
    select:focus-visible {
      outline: 3px solid rgba(52, 104, 192, 0.25);
      outline-offset: 2px;
    }

    .app-header {
      display: flex;
      align-items: center;
      min-height: 58px;
      padding: 0 28px;
      border-bottom: 1px solid #dfe3e8;
      background: #ffffff;
    }

    .brand {
      margin-right: 34px;
      color: #172034;
      font-size: 1.05rem;
      font-weight: 760;
      text-decoration: none;
    }

    .app-nav {
      display: flex;
      align-self: stretch;
      gap: 26px;
    }

    .app-nav a {
      display: flex;
      align-items: center;
      border-bottom: 2px solid transparent;
      color: #5d6675;
      font-size: 0.9rem;
      font-weight: 650;
      text-decoration: none;
    }

    .app-nav a[aria-current="page"] {
      border-color: #3468c0;
      color: #1d4f9f;
    }

    .connection-state {
      display: flex;
      align-items: center;
      gap: 7px;
      margin-left: auto;
      color: #687282;
      font-size: 0.82rem;
    }

    .connection-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #7b8491;
    }

    .connection-state[data-state="live"] .connection-dot {
      background: #23815c;
    }

    .connection-state[data-state="error"] .connection-dot {
      background: #c33e42;
    }

    main {
      width: min(1600px, 100%);
      margin: 0 auto;
      padding: 26px 28px 40px;
    }

    .title-row {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 23px;
    }

    h1 {
      margin: 0;
      color: #172034;
      font-size: 2rem;
      line-height: 1.2;
      letter-spacing: 0;
    }

    .last-updated {
      min-height: 21px;
      margin: 6px 0 0;
      color: #687282;
      font-size: 0.86rem;
    }

    .page-actions {
      display: flex;
      flex: 0 0 auto;
      gap: 9px;
    }

    .page-actions button,
    .button-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0 14px;
      text-decoration: none;
      white-space: nowrap;
    }

    .page-actions button:disabled {
      cursor: wait;
      opacity: 0.65;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(5, minmax(110px, 1fr));
      margin-bottom: 23px;
      border-top: 1px solid #dfe3e8;
      border-bottom: 1px solid #dfe3e8;
      background: #ffffff;
    }

    .metric {
      min-width: 0;
      padding: 16px 18px;
      border-right: 1px solid #e8ebef;
    }

    .metric:last-child {
      border-right: 0;
    }

    .metric-label {
      display: block;
      overflow: hidden;
      color: #687282;
      font-size: 0.75rem;
      font-weight: 720;
      text-overflow: ellipsis;
      text-transform: uppercase;
      white-space: nowrap;
    }

    .metric-value {
      display: block;
      margin-top: 3px;
      color: #20242b;
      font-size: 1.55rem;
      font-weight: 730;
      line-height: 1.2;
    }

    .metric.failed .metric-value {
      color: #ad3036;
    }

    .metric.active .metric-value {
      color: #9a5d08;
    }

    .metric.completed .metric-value {
      color: #147052;
    }

    .toolbar {
      display: grid;
      grid-template-columns: minmax(240px, 1fr) 190px auto;
      align-items: end;
      gap: 12px;
      margin-bottom: 13px;
    }

    .field-label {
      display: block;
      margin-bottom: 6px;
      color: #4e5868;
      font-size: 0.78rem;
      font-weight: 700;
    }

    input,
    select {
      width: 100%;
      min-height: 40px;
      border: 1px solid #c9ced7;
      border-radius: 6px;
      background: #ffffff;
      color: #20242b;
    }

    input {
      padding: 0 12px;
    }

    select {
      padding: 0 34px 0 10px;
    }

    .result-count {
      align-self: center;
      justify-self: end;
      color: #687282;
      font-size: 0.82rem;
      white-space: nowrap;
    }

    .error-banner {
      display: none;
      margin-bottom: 12px;
      padding: 10px 12px;
      border-left: 4px solid #c33e42;
      background: #fff1f1;
      color: #84272c;
      font-size: 0.9rem;
    }

    .error-banner[data-visible="true"] {
      display: block;
    }

    .table-wrap {
      overflow-x: auto;
      border: 1px solid #d8dde4;
      border-radius: 7px;
      background: #ffffff;
    }

    table {
      width: 100%;
      min-width: 1130px;
      border-collapse: collapse;
      table-layout: fixed;
    }

    th,
    td {
      padding: 12px 11px;
      border-bottom: 1px solid #e8ebef;
      text-align: left;
      vertical-align: middle;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f1f3f6;
      color: #515b6b;
      font-size: 0.72rem;
      font-weight: 760;
      text-transform: uppercase;
    }

    td {
      color: #29313d;
      font-size: 0.84rem;
    }

    tbody tr:last-child td {
      border-bottom: 0;
    }

    tbody tr.data-row:hover td {
      background: #fafbfd;
    }

    .cell-strong {
      overflow: hidden;
      color: #172034;
      font-weight: 680;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .cell-muted {
      overflow: hidden;
      color: #687282;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 4px;
      background: #eceff3;
      color: #515b6b;
      font-size: 0.74rem;
      font-weight: 760;
      white-space: nowrap;
    }

    .status-badge.active {
      background: #fff1d6;
      color: #80500b;
    }

    .status-badge.failed {
      background: #ffe1e2;
      color: #962d32;
    }

    .status-badge.completed {
      background: #daf2e8;
      color: #17684e;
    }

    .stale-label {
      display: block;
      margin-top: 4px;
      color: #ad3036;
      font-size: 0.7rem;
      font-weight: 720;
    }

    .progress-label {
      margin-bottom: 5px;
      color: #515b6b;
      font-size: 0.74rem;
    }

    .progress-track {
      width: 100%;
      height: 6px;
      overflow: hidden;
      border-radius: 3px;
      background: #e4e7eb;
    }

    .progress-fill {
      height: 100%;
      border-radius: inherit;
      background: #3468c0;
    }

    .row-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
    }

    .row-actions a,
    .row-actions button {
      min-height: 30px;
      padding: 0 9px;
      border-radius: 5px;
      color: #255ba9;
      font-size: 0.76rem;
      font-weight: 700;
      text-decoration: none;
      white-space: nowrap;
    }

    .row-actions a {
      display: inline-flex;
      align-items: center;
      border: 1px solid transparent;
    }

    .row-actions a:hover {
      border-color: #cad8ed;
      background: #f2f6fc;
    }

    .detail-row[hidden] {
      display: none;
    }

    .detail-row td {
      padding: 0;
      background: #f7f9fc;
    }

    .detail-content {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 18px;
      padding: 17px 18px;
      border-left: 3px solid #7e9bc7;
    }

    .detail-item {
      min-width: 0;
    }

    .detail-key {
      display: block;
      margin-bottom: 4px;
      color: #687282;
      font-size: 0.7rem;
      font-weight: 750;
      text-transform: uppercase;
    }

    .detail-value {
      display: block;
      overflow-wrap: anywhere;
      color: #29313d;
      font-size: 0.82rem;
    }

    .detail-error {
      grid-column: 1 / -1;
      margin: 0;
      padding: 10px 12px;
      overflow-x: auto;
      border-left: 3px solid #c33e42;
      background: #fff1f1;
      color: #84272c;
      font: 0.78rem/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
      white-space: pre-wrap;
    }

    .empty-state {
      display: none;
      min-height: 180px;
      place-items: center;
      border: 1px solid #d8dde4;
      border-radius: 7px;
      background: #ffffff;
      color: #687282;
      text-align: center;
    }

    .empty-state[data-visible="true"] {
      display: grid;
    }

    @media (max-width: 800px) {
      .app-header {
        flex-wrap: wrap;
        gap: 0;
        padding: 0 16px;
      }

      .brand {
        min-height: 54px;
        display: flex;
        align-items: center;
        margin-right: 22px;
      }

      .app-nav {
        min-height: 54px;
        gap: 18px;
      }

      .connection-state {
        width: 100%;
        min-height: 32px;
        margin: 0;
        border-top: 1px solid #edf0f3;
      }

      main {
        padding: 20px 16px 32px;
      }

      .title-row {
        align-items: stretch;
        flex-direction: column;
      }

      h1 {
        font-size: 1.6rem;
      }

      .page-actions {
        width: min(100%, 360px);
      }

      .page-actions button,
      .page-actions .button-link {
        flex: 1;
        min-width: 0;
      }

      .metrics {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .metric {
        border-bottom: 1px solid #e8ebef;
      }

      .metric:nth-child(2n) {
        border-right: 0;
      }

      .metric:last-child {
        grid-column: 1 / -1;
        border-bottom: 0;
      }

      .toolbar {
        grid-template-columns: 1fr;
      }

      .result-count {
        justify-self: start;
      }

      .detail-content {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

    }

    @media (max-width: 430px) {
      .brand {
        width: 100%;
        min-height: 42px;
      }

      .app-nav {
        min-height: 46px;
      }

      .detail-content {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <header class="app-header">
    <a class="brand" href="/">BioOps</a>
    <nav class="app-nav" aria-label="Primary navigation">
      <a href="/">Chat</a>
      <a href="/batches" aria-current="page">Batch status</a>
    </nav>
    <div id="connection-state" class="connection-state" data-state="loading">
      <span class="connection-dot" aria-hidden="true"></span>
      <span id="connection-text">Loading data</span>
    </div>
  </header>

  <main>
    <div class="title-row">
      <div>
        <h1>Batch status</h1>
        <p id="last-updated" class="last-updated">Waiting for the first update</p>
      </div>
      <div class="page-actions">
        <button id="refresh-button" type="button">Refresh</button>
        <a id="download-link" class="button-link" href="/batch-status.csv">
          Download CSV
        </a>
      </div>
    </div>

    <section class="metrics" aria-label="Batch status summary">
      <div class="metric">
        <span class="metric-label">Total</span>
        <strong id="metric-total" class="metric-value">0</strong>
      </div>
      <div class="metric active">
        <span class="metric-label">Active</span>
        <strong id="metric-active" class="metric-value">0</strong>
      </div>
      <div class="metric failed">
        <span class="metric-label">Failed</span>
        <strong id="metric-failed" class="metric-value">0</strong>
      </div>
      <div class="metric completed">
        <span class="metric-label">Completed</span>
        <strong id="metric-completed" class="metric-value">0</strong>
      </div>
      <div class="metric">
        <span class="metric-label">Stale active</span>
        <strong id="metric-stale" class="metric-value">0</strong>
      </div>
    </section>

    <section class="toolbar" aria-label="Batch filters">
      <label>
        <span class="field-label">Search</span>
        <input
          id="search-input"
          type="search"
          placeholder="Batch, workflow, sample, or step"
          autocomplete="off"
        >
      </label>
      <label>
        <span class="field-label">State</span>
        <select id="status-filter">
          <option value="">All states</option>
          <option value="active">Active</option>
          <option value="failed">Failed</option>
          <option value="completed">Completed</option>
          <option value="stale">Stale active</option>
        </select>
      </label>
      <span id="result-count" class="result-count">0 workflows</span>
    </section>

    <div id="error-banner" class="error-banner" role="alert"></div>

    <div id="table-wrap" class="table-wrap">
      <table>
        <colgroup>
          <col style="width: 10%">
          <col style="width: 15%">
          <col style="width: 11%">
          <col style="width: 9%">
          <col style="width: 10%">
          <col style="width: 15%">
          <col style="width: 10%">
          <col style="width: 10%">
          <col style="width: 10%">
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Batch</th>
            <th scope="col">Workflow</th>
            <th scope="col">Samples</th>
            <th scope="col">Status</th>
            <th scope="col">Progress</th>
            <th scope="col">Current step</th>
            <th scope="col">Started</th>
            <th scope="col">Last update</th>
            <th scope="col"><span class="visually-hidden">Actions</span></th>
          </tr>
        </thead>
        <tbody id="batch-rows"></tbody>
      </table>
    </div>

    <div id="empty-state" class="empty-state">
      <p>No workflows match the current filters.</p>
    </div>

  </main>

  <script>
    const searchInput = document.getElementById("search-input");
    const statusFilter = document.getElementById("status-filter");
    const refreshButton = document.getElementById("refresh-button");
    const downloadLink = document.getElementById("download-link");
    const rowsElement = document.getElementById("batch-rows");
    const tableWrap = document.getElementById("table-wrap");
    const emptyState = document.getElementById("empty-state");
    const errorBanner = document.getElementById("error-banner");
    const resultCount = document.getElementById("result-count");
    const lastUpdated = document.getElementById("last-updated");
    const connectionState = document.getElementById("connection-state");
    const connectionText = document.getElementById("connection-text");
    const metrics = {
      total: document.getElementById("metric-total"),
      active: document.getElementById("metric-active"),
      failed: document.getElementById("metric-failed"),
      completed: document.getElementById("metric-completed"),
      stale: document.getElementById("metric-stale")
    };
    let searchTimer;

    function createElement(tagName, className, text) {
      const element = document.createElement(tagName);
      if (className) {
        element.className = className;
      }
      if (text !== undefined) {
        element.textContent = text;
      }
      return element;
    }

    function statusGroup(status) {
      const clean = String(status || "").toLowerCase();
      if (["running", "pending"].includes(clean)) {
        return "active";
      }
      if (["failed", "error"].includes(clean)) {
        return "failed";
      }
      if (["succeeded", "completed"].includes(clean)) {
        return "completed";
      }
      return "other";
    }

    function externalHttpUrl(value) {
      if (!value) {
        return "";
      }
      try {
        const url = new URL(value, window.location.origin);
        return ["http:", "https:"].includes(url.protocol) ? url.href : "";
      } catch (error) {
        return "";
      }
    }

    function formatTimestamp(value) {
      if (!value) {
        return "Not available";
      }
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return value;
      }
      return new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Europe/Moscow"
      }).format(date) + " MSK";
    }

    function formatRuntime(startedAt, finishedAt) {
      if (!startedAt) {
        return "Not started";
      }
      const start = new Date(startedAt);
      const end = finishedAt ? new Date(finishedAt) : new Date();
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
        return "Not available";
      }
      const minutes = Math.max(0, Math.floor((end - start) / 60000));
      const hours = Math.floor(minutes / 60);
      const remainder = minutes % 60;
      if (hours > 0) {
        return `${hours}h ${remainder}m`;
      }
      return `${remainder}m`;
    }

    function progressPercent(progress, status) {
      const value = String(progress || "").trim();
      const percentMatch = value.match(/^(\\d+(?:\\.\\d+)?)%$/);
      if (percentMatch) {
        return Math.min(100, Math.max(0, Number(percentMatch[1])));
      }
      const fractionMatch = value.match(/^(\\d+)\\s*\\/\\s*(\\d+)$/);
      if (fractionMatch && Number(fractionMatch[2]) > 0) {
        return Math.min(
          100,
          Math.round(Number(fractionMatch[1]) / Number(fractionMatch[2]) * 100)
        );
      }
      return statusGroup(status) === "completed" ? 100 : 0;
    }

    function appendTextCell(row, value, className, fallback = "-") {
      const cell = createElement("td", className, value || fallback);
      cell.title = value || fallback;
      row.appendChild(cell);
      return cell;
    }

    function appendDetail(container, key, value) {
      const item = createElement("div", "detail-item");
      item.append(
        createElement("span", "detail-key", key),
        createElement("span", "detail-value", value || "-")
      );
      container.appendChild(item);
    }

    function renderRow(item) {
      const row = createElement("tr", "data-row");
      appendTextCell(row, item.batch_id, "cell-strong");
      appendTextCell(row, item.workflow_name, "cell-strong");
      appendTextCell(row, item.sample_ids, "cell-muted");

      const statusCell = createElement("td");
      statusCell.appendChild(
        createElement(
          "span",
          `status-badge ${statusGroup(item.status)}`,
          item.status || "Unknown"
        )
      );
      if (item.is_stale) {
        statusCell.appendChild(createElement("span", "stale-label", "Stale"));
      }
      row.appendChild(statusCell);

      const progressCell = createElement("td");
      const percent = progressPercent(item.progress, item.status);
      progressCell.appendChild(
        createElement("div", "progress-label", item.progress || "Not reported")
      );
      const progressTrack = createElement("div", "progress-track");
      progressTrack.setAttribute("role", "progressbar");
      progressTrack.setAttribute("aria-valuemin", "0");
      progressTrack.setAttribute("aria-valuemax", "100");
      progressTrack.setAttribute("aria-valuenow", String(percent));
      const progressFill = createElement("div", "progress-fill");
      progressFill.style.width = `${percent}%`;
      progressTrack.appendChild(progressFill);
      progressCell.appendChild(progressTrack);
      row.appendChild(progressCell);

      appendTextCell(row, item.current_step, "cell-muted", "Waiting");
      appendTextCell(row, formatTimestamp(item.started_at), "cell-muted");
      appendTextCell(row, formatTimestamp(item.last_checked_at), "cell-muted");

      const actionsCell = createElement("td");
      const actions = createElement("div", "row-actions");
      const argoUrl = externalHttpUrl(item.argo_url);
      if (argoUrl) {
        const argoLink = createElement("a", "", "Argo");
        argoLink.href = argoUrl;
        argoLink.target = "_blank";
        argoLink.rel = "noopener noreferrer";
        argoLink.title = "Open workflow in Argo";
        actions.appendChild(argoLink);
      }
      const detailsButton = createElement("button", "", "Details");
      detailsButton.type = "button";
      detailsButton.setAttribute("aria-expanded", "false");
      actions.appendChild(detailsButton);
      actionsCell.appendChild(actions);
      row.appendChild(actionsCell);

      const detailRow = createElement("tr", "detail-row");
      detailRow.hidden = true;
      const detailCell = createElement("td");
      detailCell.colSpan = 9;
      const detailContent = createElement("div", "detail-content");
      appendDetail(detailContent, "Template", item.workflow_template);
      appendDetail(detailContent, "Stage", item.stage);
      appendDetail(detailContent, "Mode", item.mode);
      appendDetail(
        detailContent,
        "Runtime",
        formatRuntime(item.started_at, item.finished_at)
      );
      appendDetail(detailContent, "Created", formatTimestamp(item.created_at));
      appendDetail(detailContent, "Finished", formatTimestamp(item.finished_at));
      appendDetail(detailContent, "Current step", item.current_step);
      appendDetail(detailContent, "Samples", item.sample_ids);
      if (item.error_message) {
        detailContent.appendChild(
          createElement("pre", "detail-error", item.error_message)
        );
      }
      detailCell.appendChild(detailContent);
      detailRow.appendChild(detailCell);

      detailsButton.addEventListener("click", () => {
        const willOpen = detailRow.hidden;
        detailRow.hidden = !willOpen;
        detailsButton.setAttribute("aria-expanded", String(willOpen));
        detailsButton.textContent = willOpen ? "Close" : "Details";
      });

      return [row, detailRow];
    }

    function updateDownloadLink() {
      const params = new URLSearchParams();
      const search = searchInput.value.trim();
      const status = statusFilter.value;
      if (search) {
        params.set("search", search);
      }
      if (status) {
        params.set("status", status);
      }
      const suffix = params.toString();
      downloadLink.href = suffix ? `/batch-status.csv?${suffix}` : "/batch-status.csv";
    }

    function render(payload) {
      rowsElement.replaceChildren();
      payload.items.forEach((item) => {
        rowsElement.append(...renderRow(item));
      });

      Object.entries(payload.summary).forEach(([key, value]) => {
        if (metrics[key]) {
          metrics[key].textContent = String(value);
        }
      });

      const noun = payload.matching === 1 ? "workflow" : "workflows";
      resultCount.textContent = `${payload.matching} ${noun}`;
      tableWrap.hidden = payload.items.length === 0;
      emptyState.dataset.visible = String(payload.items.length === 0);
      lastUpdated.textContent = payload.latest_update
        ? `SQLite last updated ${formatTimestamp(payload.latest_update)}`
        : "SQLite contains no workflow updates yet";
      connectionState.dataset.state = "live";
      connectionText.textContent = "SQLite connected";
      errorBanner.dataset.visible = "false";
      errorBanner.textContent = "";
    }

    async function loadBatches() {
      refreshButton.disabled = true;
      refreshButton.textContent = "Refreshing";
      updateDownloadLink();

      const params = new URLSearchParams({ limit: "250" });
      const search = searchInput.value.trim();
      const status = statusFilter.value;
      if (search) {
        params.set("search", search);
      }
      if (status) {
        params.set("status", status);
      }

      try {
        const response = await fetch(`/api/batches?${params}`);
        if (!response.ok) {
          throw new Error(`Batch status request failed (${response.status})`);
        }
        render(await response.json());
      } catch (error) {
        connectionState.dataset.state = "error";
        connectionText.textContent = "Data unavailable";
        errorBanner.textContent = String(error);
        errorBanner.dataset.visible = "true";
      } finally {
        refreshButton.disabled = false;
        refreshButton.textContent = "Refresh";
      }
    }

    refreshButton.addEventListener("click", loadBatches);
    statusFilter.addEventListener("change", loadBatches);
    searchInput.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(loadBatches, 250);
    });

    loadBatches();
    setInterval(loadBatches, 30000);
  </script>
</body>
</html>
"""
