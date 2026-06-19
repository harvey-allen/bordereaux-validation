(function initTaskpaneRulesEngine(global) {
  async function openRulesEngine(deps) {
    const {
      CONFIG,
      APP_LOGO_URL,
      formatPackLabel,
      setStatus,
    } = deps;

    const rulesButton = document.getElementById("rulesEngine");
    if (rulesButton) {
      rulesButton.disabled = true;
    }

    try {
      setStatus("Loading rules engine...");
      const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
      const rulesUrl = new URL(`${CONFIG.BACKEND_URL}/api/v1/rules-engine`);
      // Always fetch ALL rules so users can switch between packs in the filter
      // Do not set test_pack parameter

      const response = await fetch(rulesUrl.toString(), {
        method: "GET",
        cache: "no-store",
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        throw new Error(errorText || `HTTP ${response.status}`);
      }

      const payload = await response.json().catch(() => ({}));
      const rules = Array.isArray(payload?.rules) ? payload.rules : [];
      const packs = Array.isArray(payload?.packs) ? payload.packs : [];
      const nowStr = new Date().toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
      const packLabel = formatPackLabel(selectedPack || "all Packs");

      const win = window.open("", "_blank");
      if (!win) {
        setStatus("Could not open new tab — popup blocked.", true);
        return;
      }

      const safeJson = (value) => JSON.stringify(value)
        .replace(/</g, "\\u003c")
        .replace(/>/g, "\\u003e")
        .replace(/&/g, "\\u0026")
        .replace(/\u2028/g, "\\u2028")
        .replace(/\u2029/g, "\\u2029");
      const escapeHtml = (s) => String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#39;");

      const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Rules Engine</title>
  <style>
    :root {
      --bg: #f6f8fb;
      --surface: #ffffff;
      --border: #e5e7eb;
      --text-1: #0f172a;
      --text-2: #475569;
      --text-3: #64748b;
      --accent: #4f46e5;
      --accent-soft: #eef2ff;
      --ok-bg: #dcfce7;
      --ok-fg: #166534;
      --warn-bg: #fef3c7;
      --warn-fg: #92400e;
      --err-bg: #ffedd5;
      --err-fg: #9a3412;
      --crit-bg: #fee2e2;
      --crit-fg: #991b1b;
      --radius: 10px;
      --rule-columns: minmax(250px, 1.6fr) minmax(120px, 0.7fr) minmax(150px, 0.9fr) minmax(220px, 1.2fr);
      --shadow: 0 1px 2px rgba(15,23,42,.04), 0 4px 16px rgba(15,23,42,.06);
      --font: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --nav-bg: #0f1117;
      --nav-text: #c9cdd4;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text-1); font-family: var(--font); }
    .nav { display:flex; align-items:center; gap:16px; padding:0 24px; height:52px; background:var(--nav-bg); border-bottom:1px solid #1e2028; position:sticky; top:0; z-index:100; }
    .nav-logo { display:flex; align-items:center; gap:8px; color:#fff; font-size:14px; font-weight:600; letter-spacing:-.2px; text-decoration:none; }
    .nav-logo img { width:20px; height:20px; object-fit:contain; border-radius:5px; flex-shrink:0; }
    .nav-divider { width:1px; height:20px; background:#2e3140; }
    .nav-title { color:var(--nav-text); font-size:13px; }
    .nav-spacer { flex:1; }
    .nav-meta { color:#8a92a6; font-size:12px; }
    .nav-badge { padding:3px 8px; border-radius:4px; font-size:11px; font-weight:600; background:#1e2028; color:var(--nav-text); border:1px solid #2e3140; }
    .page { max-width: 1500px; margin: 0 auto; padding: 16px; }
    .page-header { display:flex; align-items:flex-start; justify-content:space-between; margin-bottom:14px; }
    .page-header h1 { margin:0; font-size:20px; font-weight:700; letter-spacing:-.3px; }
    .page-header p { margin:4px 0 0; color:var(--text-2); font-size:13px; }
    .search {
      width: 100%; border: 1px solid var(--border); border-radius: 8px;
      padding: 9px 12px; font-size: 13px; background: #fff;
    }
    .select {
      border: 1px solid var(--border); border-radius: 8px;
      padding: 9px 10px; font-size: 13px; background: #fff; min-width: 170px;
    }
    .summary { color: var(--text-3); font-size: 12px; white-space: nowrap; }
    .side-controls { margin-top: 12px; display: grid; gap: 8px; }
    .layout {
      display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 16px;
    }
    .sidebar {
      position: sticky; top: 84px; max-height: calc(100vh - 100px); overflow: auto;
      background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow);
    }
    .side-head { padding: 12px 14px; border-bottom: 1px solid var(--border); }
    .side-head h2 { margin: 0; font-size: 13px; }
    .side-head p { margin: 4px 0 0; color: var(--text-3); font-size: 11px; }
    .index-list { padding: 8px; display: grid; gap: 4px; }
    .index-link {
      display: flex; justify-content: space-between; gap: 10px;
      text-decoration: none; color: var(--text-2); font-size: 12px;
      padding: 8px 10px; border-radius: 7px;
    }
    .index-link:hover { background: #f1f5f9; color: var(--text-1); }
    .index-count { color: var(--text-3); font-variant-numeric: tabular-nums; }
    .content { min-width: 0; }
    .group {
      background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
      box-shadow: var(--shadow); margin-bottom: 12px; overflow: hidden;
    }
    .group-head { padding: 12px 14px; border-bottom: 1px solid var(--border); background: #fcfcff; }
    .group-title { margin: 0; font-size: 14px; }
    .group-sub { margin: 4px 0 0; color: var(--text-3); font-size: 11px; }
    .rule-grid { width: 100%; }
    .rule-grid-head,
    .rule-main {
      display: grid;
      grid-template-columns: var(--rule-columns);
    }
    .rule-grid-head {
      background: #fafafa;
      border-bottom: 1px solid var(--border);
    }
    .rule-head-cell,
    .rule-cell,
    .desc-cell {
      padding: 10px 12px;
      font-size: 12px;
      vertical-align: top;
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    .rule-head-cell {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .04em;
      color: var(--text-3);
      font-weight: 600;
    }
    .rule-main { border-bottom: none; }
    .rule-block { border-bottom: 1px solid var(--border); }
    .rule-block:last-child { border-bottom: none; }
    .desc-cell {
      grid-column: 1 / -1;
      padding-top: 0; padding-bottom: 12px; color: var(--text-2);
      line-height: 1.45;
    }
    .desc-label { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); margin-right: 8px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
    .badge { display: inline-flex; align-items: center; border-radius: 999px; padding: 3px 9px; font-size: 11px; font-weight: 600; }
    .sev-INFO { background: #e2e8f0; color: #334155; }
    .sev-WARNING { background: var(--warn-bg); color: var(--warn-fg); }
    .sev-ERROR { background: var(--err-bg); color: var(--err-fg); }
    .sev-CRITICAL { background: var(--crit-bg); color: var(--crit-fg); }
    .empty {
      background: var(--surface); border: 1px dashed var(--border); border-radius: var(--radius);
      color: var(--text-3); padding: 28px; text-align: center; font-size: 13px;
    }
    @media (max-width: 1024px) {
      .layout { grid-template-columns: 1fr; }
      .sidebar { position: static; max-height: none; }
    }
    @media (max-width: 860px) {
      :root {
        --rule-columns: minmax(0, 1fr) minmax(110px, 0.8fr);
      }
      .rule-grid-head,
      .rule-main {
        grid-template-columns: var(--rule-columns);
      }
      .rule-head-cell:nth-child(3),
      .rule-head-cell:nth-child(4),
      .rule-cell--type,
      .rule-cell--pack {
        grid-column: 1 / -1;
        padding-top: 0;
      }
      .rule-cell--severity {
        justify-self: start;
      }
    }
  </style>
</head>
<body>
  <nav class="nav">
    <a class="nav-logo" href="#">
      <img src="${escapeHtml(APP_LOGO_URL)}" alt="Axios logo" />
      Axios
    </a>
    <div class="nav-divider"></div>
    <span class="nav-title">Reporting Validation</span>
    <div class="nav-spacer"></div>
    <span class="nav-meta">Pack: <strong style="color:#fff">${escapeHtml(packLabel)}</strong></span>
    <div class="nav-divider"></div>
    <span class="nav-meta">${escapeHtml(nowStr)}</span>
    <span class="nav-badge" id="summary"></span>
  </nav>

  <div class="page">
    <div class="page-header">
      <div>
        <h1>Rules Engine</h1>
        <p>Complete catalogue of active validation rules grouped by field and sourced directly from registered test packs.</p>
      </div>
    </div>

    <div class="layout">
      <aside class="sidebar">
        <div class="side-head">
          <h2>Field Index</h2>
          <p>Grouped alphabetically by target column</p>
          <div class="side-controls">
            <input id="search" class="search" type="search" placeholder="Search" />
            <select id="packFilter" class="select"></select>
          </div>
        </div>
        <nav class="index-list" id="indexList"></nav>
      </aside>

      <main class="content" id="groupsContainer"></main>
    </div>
  </div>

  <script>
    (function () {
      const ALL_RULES = ${safeJson(rules)};
      const PACKS = ${safeJson(packs)};
      const INITIAL_PACK = ${safeJson(selectedPack || "")};

      const searchInput = document.getElementById("search");
      const packFilter = document.getElementById("packFilter");
      const indexList = document.getElementById("indexList");
      const groupsContainer = document.getElementById("groupsContainer");
      const summary = document.getElementById("summary");

      const norm = (value) => String(value || "").trim().toLowerCase();
      const clean = (value) => String(value || "").trim();
      const formatTestTypeLabel = (value) => String(value || "").trim().replace(/[_-]+/g, " ");
      const slug = (value) => clean(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "field";

      function setupPackFilter() {
        packFilter.innerHTML = "";
        const allOption = document.createElement("option");
        allOption.value = "";
        allOption.textContent = "All packs";
        packFilter.appendChild(allOption);

        PACKS.forEach((pack) => {
          const opt = document.createElement("option");
          opt.value = String(pack || "");
          opt.textContent = String(pack || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
          packFilter.appendChild(opt);
        });

        if (INITIAL_PACK && PACKS.includes(INITIAL_PACK)) {
          packFilter.value = INITIAL_PACK;
        }
      }

      function getFilteredRules() {
        const q = norm(searchInput.value);
        const selected = norm(packFilter.value);

        return ALL_RULES
          .filter((rule) => {
            const packNames = String(rule.pack || "")
              .split(",")
              .map((item) => norm(item))
              .filter(Boolean);
            if (selected && !packNames.includes(selected)) return false;

            if (!q) return true;
            const haystack = [
              rule.rule_id,
              rule.target_column,
              rule.description,
              rule.severity,
              formatTestTypeLabel(rule.test_type),
              rule.pack,
            ].map(norm).join(" ");
            return haystack.includes(q);
          })
          .sort((a, b) => {
            const byCol = compareFieldNames(a.target_column, b.target_column);
            if (byCol !== 0) return byCol;
            const byRule = clean(a.rule_id).localeCompare(clean(b.rule_id), undefined, { sensitivity: "base" });
            if (byRule !== 0) return byRule;
            return clean(a.pack).localeCompare(clean(b.pack), undefined, { sensitivity: "base" });
          });
      }

      function compareFieldNames(leftValue, rightValue) {
        const left = clean(leftValue);
        const right = clean(rightValue);
        const leftHasSpecialChars = /[^a-z0-9\s]/i.test(left);
        const rightHasSpecialChars = /[^a-z0-9\s]/i.test(right);

        if (leftHasSpecialChars !== rightHasSpecialChars) {
          return leftHasSpecialChars ? 1 : -1;
        }

        return left.localeCompare(right, undefined, { sensitivity: "base" });
      }

      function groupByColumn(filteredRules) {
        const grouped = new Map();
        filteredRules.forEach((rule) => {
          const column = clean(rule.target_column) || "(unmapped)";
          if (!grouped.has(column)) grouped.set(column, []);
          grouped.get(column).push(rule);
        });

        return Array.from(grouped.entries())
          .sort((a, b) => compareFieldNames(a[0], b[0]))
          .map(([column, rows]) => ({ column, rows }));
      }

      function renderIndex(groups) {
        indexList.innerHTML = "";
        if (!groups.length) {
          const item = document.createElement("div");
          item.className = "index-link";
          item.textContent = "No fields";
          indexList.appendChild(item);
          return;
        }

        groups.forEach((group) => {
          const a = document.createElement("a");
          a.className = "index-link";
          a.href = "#field-" + slug(group.column);

          const label = document.createElement("span");
          label.textContent = group.column;
          const count = document.createElement("span");
          count.className = "index-count";
          count.textContent = String(group.rows.length);

          a.appendChild(label);
          a.appendChild(count);
          indexList.appendChild(a);
        });
      }

      function scrollGroupIntoView(groupId) {
        const target = document.getElementById(groupId);
        if (!target) return;

        target.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
      }

      function severityClass(sev) {
        const normalized = clean(sev).toUpperCase();
        if (normalized === "CRITICAL") return "sev-CRITICAL";
        if (normalized === "WARNING") return "sev-WARNING";
        if (normalized === "INFO") return "sev-INFO";
        return "sev-ERROR";
      }

      function renderGroups(groups, filteredRules) {
        groupsContainer.innerHTML = "";
        summary.textContent = String(filteredRules.length) + " rules • " + String(groups.length) + " fields";

        if (!groups.length) {
          const empty = document.createElement("div");
          empty.className = "empty";
          empty.textContent = "No rules match your current filters.";
          groupsContainer.appendChild(empty);
          return;
        }

        groups.forEach((group) => {
          const section = document.createElement("section");
          section.className = "group";
          section.id = "field-" + slug(group.column);

          const head = document.createElement("div");
          head.className = "group-head";
          const title = document.createElement("h3");
          title.className = "group-title";
          title.textContent = group.column;
          const sub = document.createElement("p");
          sub.className = "group-sub";
          sub.textContent = String(group.rows.length) + " rule" + (group.rows.length === 1 ? "" : "s");
          head.appendChild(title);
          head.appendChild(sub);

          const grid = document.createElement("div");
          grid.className = "rule-grid";

          const gridHead = document.createElement("div");
          gridHead.className = "rule-grid-head";
          ["Rule ID", "Severity", "Test Type", "Pack"].forEach((heading) => {
            const cell = document.createElement("div");
            cell.className = "rule-head-cell";
            cell.textContent = heading;
            gridHead.appendChild(cell);
          });
          grid.appendChild(gridHead);

          group.rows.forEach((rule) => {
            const block = document.createElement("div");
            block.className = "rule-block";

            const row = document.createElement("div");
            row.className = "rule-main";

            const tdId = document.createElement("div");
            tdId.className = "rule-cell mono";
            tdId.textContent = clean(rule.rule_id) || "—";

            const tdSeverity = document.createElement("div");
            tdSeverity.className = "rule-cell rule-cell--severity";
            const sevBadge = document.createElement("span");
            sevBadge.className = "badge " + severityClass(rule.severity);
            sevBadge.textContent = clean(rule.severity) || "ERROR";
            tdSeverity.appendChild(sevBadge);

            const tdType = document.createElement("div");
            tdType.className = "rule-cell rule-cell--type";
            tdType.textContent = formatTestTypeLabel(clean(rule.test_type)) || "—";

            const tdPack = document.createElement("div");
            tdPack.className = "rule-cell rule-cell--pack";
            tdPack.textContent = clean(rule.pack)
              ? String(rule.pack).replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
              : "—";

            row.appendChild(tdId);
            row.appendChild(tdSeverity);
            row.appendChild(tdType);
            row.appendChild(tdPack);
            block.appendChild(row);

            const descTd = document.createElement("div");
            descTd.className = "desc-cell";
            const label = document.createElement("span");
            label.className = "desc-label";
            label.textContent = "Description";
            const text = document.createElement("span");
            text.textContent = clean(rule.description) || "—";
            descTd.appendChild(label);
            descTd.appendChild(text);
            block.appendChild(descTd);
            grid.appendChild(block);
          });

          section.appendChild(head);
          section.appendChild(grid);
          groupsContainer.appendChild(section);
        });
      }

      function render() {
        const filtered = getFilteredRules();
        const groups = groupByColumn(filtered);
        renderIndex(groups);
        renderGroups(groups, filtered);
      }

      setupPackFilter();
      searchInput.addEventListener("input", render);
      packFilter.addEventListener("change", render);
      indexList.addEventListener("click", (event) => {
        const link = event.target.closest("a.index-link");
        if (!link) return;

        const href = String(link.getAttribute("href") || "");
        if (!href.startsWith("#")) return;

        event.preventDefault();
        const groupId = href.slice(1);
        scrollGroupIntoView(groupId);

        if (window.history && typeof window.history.replaceState === "function") {
          window.history.replaceState(null, "", href);
        } else {
          window.location.hash = groupId;
        }
      });
      render();
    })();
  </script>
</body>
</html>`;

      win.document.open();
      win.document.write(html);
      win.document.close();

      setStatus(`Rules engine opened: ${rules.length} rules loaded.`);
    } catch (error) {
      setStatus(`Rules engine failed: ${error?.message || "Unexpected error"}`, true);
    } finally {
      if (rulesButton) {
        rulesButton.disabled = false;
      }
    }
  }

  global.TaskpaneRulesEngine = {
    openRulesEngine,
  };
}(window));
