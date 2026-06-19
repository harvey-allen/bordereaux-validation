(function initTaskpaneVisualisation(global) {
  async function computeVisualisationKpisFromCurrentRun(deps, exportRows) {
    const failedUmrs = new Set((exportRows || []).map((r) => String(r.umr || "").trim()).filter(Boolean));
    const failedFields = new Set((exportRows || []).map((r) => String(r.fieldName || "").trim()).filter(Boolean));
    const failedTests = new Set((exportRows || []).map((r) => String(r.testId || "").trim()).filter(Boolean));

    let totalSubmittedUmrs = null;
    let totalFields = null;

    try {
      await Excel.run(async (context) => {
        const workbook = context.workbook;
        const sourceSheetName = deps.getLastValidationSourceSheetName();
        const worksheet = sourceSheetName
          ? workbook.worksheets.getItemOrNullObject(sourceSheetName)
          : workbook.worksheets.getActiveWorksheet();
        worksheet.load("isNullObject");
        await context.sync();
        if (worksheet.isNullObject) return;

        const usedRange = worksheet.getUsedRangeOrNullObject();
        usedRange.load(["isNullObject", "values"]);
        await context.sync();
        if (usedRange.isNullObject) return;

        const allValues = usedRange.values || [];
        if (!allValues.length) return;

        const header = allValues[0] || [];
        totalFields = header.length || null;

        const umrCol = deps.resolveReferenceColumnIndex(header, deps.getLastValidationPack() || deps.getCurrentPackSelection());
        if (umrCol >= 0) {
          const umrSet = new Set();
          for (let i = 1; i < allValues.length; i += 1) {
            const value = allValues[i] && allValues[i][umrCol];
            if (value !== null && value !== undefined && String(value).trim() !== "") {
              umrSet.add(String(value).trim());
            }
          }
          totalSubmittedUmrs = umrSet.size;
        }
      });
    } catch {
      // best-effort only
    }

    const executedTests = deps.getLastValidationExecutedTests();
    const totalTests = Array.isArray(executedTests) ? executedTests.length : null;

    const submissionsFailedPct = totalSubmittedUmrs ? ((failedUmrs.size / totalSubmittedUmrs) * 100) : null;
    const fieldsFailedPct = totalFields ? ((failedFields.size / totalFields) * 100) : null;
    const testsFailedPct = totalTests ? ((failedTests.size / totalTests) * 100) : null;
    const testsPassedPct = totalTests ? ((1 - (failedTests.size / totalTests)) * 100) : null;

    return {
      submissions_failed: failedUmrs.size,
      submissions_failed_pct: submissionsFailedPct,
      fields_failed: failedFields.size,
      fields_failed_pct: fieldsFailedPct,
      tests_failed: failedTests.size,
      tests_failed_pct: testsFailedPct,
      tests_passed_pct: testsPassedPct,
      total_submissions: totalSubmittedUmrs,
      total_fields: totalFields,
      total_tests: totalTests,
      computed_at: new Date().toISOString(),
      failed_sets: {
        submissions: failedUmrs,
        fields: failedFields,
        tests: failedTests,
      },
    };
  }

  async function visualiseValidationResults(deps) {
    const visualiseButton = document.getElementById("visualiseResults");

    await deps.ensureValidationResultsLoadedForActiveSheet();

    const loadedResults = deps.getLastValidationResults();
    if (!loadedResults || loadedResults.length === 0) {
      deps.setStatus("No validation results to visualise. Please run validation first.", true);
      return;
    }

    if (visualiseButton) {
      visualiseButton.disabled = true;
    }

    try {
      deps.setStatus("Preparing front-end visualisation...");
      const exportRows = await deps.buildFailureExportRows();

      const computedKpis = await computeVisualisationKpisFromCurrentRun(deps, exportRows);
      const failedUmrs = computedKpis.failed_sets?.submissions || new Set();
      const failedFields = computedKpis.failed_sets?.fields || new Set();
      const failedTests = computedKpis.failed_sets?.tests || new Set();
      const totalSubmittedUmrs = computedKpis.total_submissions;
      const totalFields = computedKpis.total_fields;
      const totalTests = computedKpis.total_tests;

      const formatPercent = (numerator, denominator) => {
        if (!denominator) return "N/A";
        return `${((numerator / denominator) * 100).toFixed(1)}%`;
      };

      const currentKpiValues = {
        submissions_failed: computedKpis.submissions_failed,
        submissions_failed_pct: computedKpis.submissions_failed_pct,
        fields_failed: computedKpis.fields_failed,
        fields_failed_pct: computedKpis.fields_failed_pct,
        tests_failed: computedKpis.tests_failed,
        tests_failed_pct: computedKpis.tests_failed_pct,
        tests_passed_pct: computedKpis.tests_passed_pct,
        total_submissions: computedKpis.total_submissions,
        total_fields: computedKpis.total_fields,
        total_tests: computedKpis.total_tests,
      };

      let previousVersionSummary = null;
      let trendSeries = [];

      try {
        const excelUserEmail = deps.getExcelUserEmail();
        const selectedPack = String(deps.getLastValidationPack() || deps.getSelectedPack() || "").trim().toLowerCase();
        if (excelUserEmail && selectedPack) {
          const { workbookName, sheetName } = await deps.getCurrentResultsScope();
          const comparisonQuery = new URLSearchParams({
            workbook_name: workbookName,
            sheet_name: sheetName,
            test_pack: selectedPack,
          });

          const comparisonResponse = await fetch(`${deps.CONFIG.BACKEND_URL}/api/v1/results/versions/comparison?${comparisonQuery.toString()}`, {
            method: "GET",
            headers: {
              "X-Excel-User-Email": excelUserEmail,
            },
            cache: "no-store",
          });

          if (comparisonResponse.ok) {
            const comparisonPayload = await comparisonResponse.json().catch(() => ({}));
            previousVersionSummary = comparisonPayload?.previous_version || null;
            trendSeries = Array.isArray(comparisonPayload?.trend) ? comparisonPayload.trend : [];
          }
        }
      } catch {
        // best-effort only
      }

      if (trendSeries.length > 0 && Number.isFinite(currentKpiValues.tests_passed_pct)) {
        trendSeries = [
          ...trendSeries,
          {
            id: "current",
            version_name: "Current",
            workbook_name: "Current",
            sheet_name: "Current worksheet",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            test_passed_pct: currentKpiValues.tests_passed_pct,
            submissions_failed_pct: currentKpiValues.submissions_failed_pct,
            fields_failed_pct: currentKpiValues.fields_failed_pct,
            is_current: true,
          },
        ];
      }

      const previousKpis = previousVersionSummary?.kpis || null;
      const buildDelta = (currentValue, previousValue, isPercent) => {
        if (!Number.isFinite(currentValue) || !Number.isFinite(previousValue)) {
          return null;
        }
        const delta = currentValue - previousValue;
        if (Math.abs(delta) < 0.0001) {
          return { label: "No change", tone: "neutral" };
        }
        if (isPercent) {
          return {
            label: `${delta > 0 ? "▲" : "▼"} ${Math.abs(delta).toFixed(1)}%`,
            tone: delta > 0 ? "up" : "down",
          };
        }
        return {
          label: `${delta > 0 ? "▲" : "▼"} ${Math.abs(Math.round(delta))}`,
          tone: delta > 0 ? "up" : "down",
        };
      };

      const kpis = [
        {
          key: "submissions_failed",
          title: "Submissions Failed",
          value: String(failedUmrs.size),
          delta: buildDelta(currentKpiValues.submissions_failed, Number(previousKpis?.submissions_failed), false),
        },
        {
          key: "submissions_failed_pct",
          title: "Submissions Failed %",
          value: formatPercent(failedUmrs.size, totalSubmittedUmrs),
          delta: buildDelta(currentKpiValues.submissions_failed_pct, Number(previousKpis?.submissions_failed_pct), true),
        },
        {
          key: "fields_failed",
          title: "Fields Failed",
          value: String(failedFields.size),
          delta: buildDelta(currentKpiValues.fields_failed, Number(previousKpis?.fields_failed), false),
        },
        {
          key: "fields_failed_pct",
          title: "Fields Failed %",
          value: formatPercent(failedFields.size, totalFields),
          delta: buildDelta(currentKpiValues.fields_failed_pct, Number(previousKpis?.fields_failed_pct), true),
        },
        {
          key: "tests_failed",
          title: "Tests Failed",
          value: String(failedTests.size),
          delta: buildDelta(currentKpiValues.tests_failed, Number(previousKpis?.tests_failed), false),
        },
        {
          key: "tests_failed_pct",
          title: "Tests Failed %",
          value: formatPercent(failedTests.size, totalTests),
          delta: buildDelta(currentKpiValues.tests_failed_pct, Number(previousKpis?.tests_failed_pct), true),
        },
      ];

      const getKpiAccent = (kpi) => {
        const raw = String(kpi?.value || "").trim();
        if (!raw.endsWith("%")) return "neutral";
        const n = Number.parseFloat(raw);
        if (!Number.isFinite(n)) return "neutral";
        if (n < 50) return "ok";
        if (n > 50) return "danger";
        return "warn";
      };

      const getKpiSub = (kpi) => {
        const title = String(kpi?.title || "").toLowerCase();
        if (title.includes("submission")) {
          return totalSubmittedUmrs ? `of ${totalSubmittedUmrs} total submissions` : "&nbsp;";
        }
        if (title.includes("field")) {
          return totalFields ? `of ${totalFields} total fields` : "&nbsp;";
        }
        if (title.includes("test")) {
          return totalTests ? `of ${totalTests} tests run` : "&nbsp;";
        }
        return "&nbsp;";
      };

      const buildSeverityDataset = (keyFn) => {
        const m = new Map();
        for (const r of exportRows) {
          const key = String(keyFn(r) || "(unknown)").trim();
          const rawSev = String(r.severity || "").toUpperCase().trim();
          const sev = rawSev === "CRITICAL" || rawSev === "WARNING" || rawSev === "ERROR" ? rawSev : "ERROR";
          if (!m.has(key)) {
            m.set(key, { label: key, WARNING: 0, ERROR: 0, CRITICAL: 0, total: 0 });
          }
          const row = m.get(key);
          row[sev] += 1;
          row.total += 1;
        }
        return Array.from(m.values()).sort((a, b) => b.total - a.total).slice(0, 10);
      };

      const fieldCounts = buildSeverityDataset((r) => r.fieldName);
      const testCounts = buildSeverityDataset((r) => r.testId);
      const umrCounts = buildSeverityDataset((r) => r.umr);

      const safeJson = (value) => JSON.stringify(value)
        .replace(/</g, "\\u003c")
        .replace(/>/g, "\\u003e")
        .replace(/&/g, "\\u0026")
        .replace(/\u2028/g, "\\u2028")
        .replace(/\u2029/g, "\\u2029");
      const datasetsJson = safeJson({ test: testCounts, trade: fieldCounts, umr: umrCounts });
      const allRowsJson = safeJson(exportRows.map((r) => ({
        umr: r.umr || "",
        testId: r.testId || "",
        fieldName: r.fieldName || "",
        severity: r.severity || "",
        exceptionId: r.exceptionId || "",
        description: r.description || "",
      })));
      const trendJson = safeJson(trendSeries.map((item) => ({
        id: item.id,
        version_name: item.version_name,
        workbook_name: item.workbook_name,
        sheet_name: item.sheet_name,
        created_at: item.created_at,
        updated_at: item.updated_at,
        test_passed_pct: item.test_passed_pct,
        submissions_failed_pct: item.submissions_failed_pct,
        fields_failed_pct: item.fields_failed_pct,
        is_current: Boolean(item.is_current),
      })));

      const backendUrl = String(deps.CONFIG.BACKEND_URL || "").trim();
      const userEmail = String(deps.getExcelUserEmail() || "").trim();
      const configJson = safeJson({ backendUrl, userEmail });

      const win = window.open("", "_blank");
      if (!win) {
        deps.setStatus("Could not open new tab — popup blocked.", true);
        return;
      }

      const escapeHtml = (s) => String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

      const nowStr = new Date().toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
      const packLabel = deps.formatPackLabel(deps.getLastValidationPack() || deps.getCurrentPackSelection() || "Unknown");
      const previousVersionLabel = previousVersionSummary
        ? String(previousVersionSummary.version_name || `${previousVersionSummary.workbook_name} / ${previousVersionSummary.sheet_name}`).trim()
        : "None";

      const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Reporting Validation — Results</title>
  <style>
    :root {
      --bg:        #f8f9fb;
      --surface:   #ffffff;
      --border:    #e3e6ea;
      --nav-bg:    #0f1117;
      --nav-text:  #c9cdd4;
      --accent:    #4f6ef7;
      --accent-lt: #eef0ff;
      --danger:    #e5484d;
      --danger-lt: #fff0f0;
      --warn:      #f59e0b;
      --warn-lt:   #fffbeb;
      --ok:        #22c55e;
      --text-1:    #111318;
      --text-2:    #5a6072;
      --text-3:    #8a92a6;
      --radius:    8px;
      --shadow:    0 1px 3px rgba(0,0,0,.07), 0 1px 2px rgba(0,0,0,.04);
      --shadow-md: 0 4px 12px rgba(0,0,0,.08);
      --font:      'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    *, *::before, *::after { box-sizing: border-box; }
    html, body { margin:0; padding:0; height:100%; }
    body { font-family: var(--font); font-size:13px; background:var(--bg); color:var(--text-1); -webkit-font-smoothing:antialiased; }

    .nav { display:flex; align-items:center; gap:16px; padding:0 24px; height:52px; background:var(--nav-bg); border-bottom:1px solid #1e2028; position:sticky; top:0; z-index:100; }
    .nav-logo { display:flex; align-items:center; gap:8px; color:#fff; font-size:14px; font-weight:600; letter-spacing:-.2px; text-decoration:none; }
    .nav-logo img { width:20px; height:20px; object-fit:contain; border-radius:5px; flex-shrink:0; }
    .nav-divider { width:1px; height:20px; background:#2e3140; }
    .nav-title { color:var(--nav-text); font-size:13px; }
    .nav-spacer { flex:1; }
    .nav-meta { color:var(--text-3); font-size:12px; }
    .nav-badge { padding:3px 8px; border-radius:4px; font-size:11px; font-weight:600; background:#1e2028; color:var(--nav-text); border:1px solid #2e3140; }

    .page { max-width:1280px; margin:0 auto; padding:24px 24px 48px; }

    .page-header { display:flex; align-items:flex-start; justify-content:space-between; margin-bottom:24px; }
    .page-header h1 { margin:0; font-size:20px; font-weight:700; letter-spacing:-.3px; }
    .page-header p { margin:4px 0 0; color:var(--text-2); font-size:13px; }

    .stat-grid { display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin-bottom:24px; }
    @media(max-width:1100px){ .stat-grid { grid-template-columns:repeat(3,1fr); } }
    .stat-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px 18px; box-shadow:var(--shadow); }
    .stat-card.danger { border-left:3px solid var(--danger); }
    .stat-card.warn { border-left:3px solid var(--warn); }
    .stat-card.ok { border-left:3px solid var(--ok); }
    .stat-card.neutral { border-left:3px solid var(--accent); }
    .stat-label { font-size:11px; font-weight:600; color:var(--text-2); text-transform:uppercase; letter-spacing:.5px; margin-bottom:8px; }
    .stat-value { font-size:28px; font-weight:700; line-height:1; letter-spacing:-.5px; color:var(--text-1); }
    .stat-sub { font-size:11px; color:var(--text-3); margin-top:5px; }
    .stat-delta { margin-top:8px; font-size:11px; font-weight:600; }
    .stat-delta.up { color:#b91c1c; }
    .stat-delta.down { color:#15803d; }
    .stat-delta.neutral { color:var(--text-3); }

    .panel { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); box-shadow:var(--shadow); margin-bottom:16px; }
    .panel-header { display:flex; align-items:center; justify-content:space-between; padding:14px 18px 12px; border-bottom:1px solid var(--border); cursor:pointer; user-select:none; transition:background .12s; }
    .panel-header:hover { background:#fafbfc; }
    .panel-title { font-size:13px; font-weight:600; color:var(--text-1); margin:0; }
    .panel-subtitle { font-size:12px; color:var(--text-3); margin-top:2px; }
    .panel-body { padding:18px; transition:max-height .3s ease, opacity .3s ease, padding .3s ease, visibility .3s ease; overflow:hidden; }
    .panel-body.collapsed { max-height:0; opacity:0; padding:0 18px; visibility:hidden; }
    .panel-collapse-btn { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border:none; background:transparent; cursor:pointer; color:var(--text-2); font-size:16px; padding:0; margin:0; transition:transform .3s ease; flex-shrink:0; }
    .panel-collapse-btn.collapsed { transform:rotate(-90deg); }

    .tab-group { display:inline-flex; gap:2px; background:#f0f2f5; border-radius:6px; padding:3px; border:1px solid var(--border); }
    .tab-btn { padding:5px 14px; border:none; background:transparent; border-radius:5px; font-size:12px; font-weight:500; color:var(--text-2); cursor:pointer; transition:background .12s, color .12s; white-space:nowrap; }
    .tab-btn.active { background:var(--surface); color:var(--text-1); box-shadow:0 1px 3px rgba(0,0,0,.1); font-weight:600; }

    .chart-wrap { padding:4px 0; }
    .bar-row { display:grid; grid-template-columns:200px 1fr 52px; align-items:center; gap:10px; padding:5px 0; border-bottom:1px solid #f3f4f6; }
    .bar-row:last-child { border-bottom:none; }
    .bar-label { font-size:12px; color:var(--text-1); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .bar-track { background:#f0f2f5; border-radius:4px; height:12px; overflow:hidden; position:relative; }
    .bar-fill { height:100%; display:flex; border-radius:4px; overflow:hidden; }
    .bar-seg { height:100%; transition:width .3s ease; }
    .bar-seg.warn { background:#fde68a; }
    .bar-seg.error { background:#fdba74; }
    .bar-seg.critical { background:#fca5a5; }
    .bar-count { font-size:12px; color:var(--text-2); font-variant-numeric:tabular-nums; text-align:right; font-weight:500; }
    .severity-legend { display:flex; gap:12px; align-items:center; margin:6px 0 12px; }
    .severity-legend-item { display:inline-flex; align-items:center; gap:6px; color:var(--text-2); font-size:11px; }
    .severity-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
    .severity-dot.warn { background:#fde68a; }
    .severity-dot.error { background:#fdba74; }
    .severity-dot.critical { background:#fca5a5; }

    .vertical-chart-wrap { display:flex; gap:12px; align-items:flex-end; padding:24px 0; min-height:280px; justify-content:center; overflow-x:auto; }
    .vertical-bar-container { display:flex; flex-direction:column; align-items:center; gap:6px; min-width:60px; }
    .vertical-bar-track { width:40px; background:#f0f2f5; border-radius:4px 4px 0 0; min-height:2px; display:flex; flex-direction:column-reverse; }
    .vertical-bar-fill { width:100%; border-radius:4px 4px 0 0; transition:height .3s ease; }
    .vertical-bar-label { font-size:11px; color:var(--text-1); text-align:center; word-break:break-word; max-width:50px; line-height:1.2; }
    .vertical-bar-value { font-size:12px; font-weight:600; color:var(--text-1); }
    .vertical-chart-empty { text-align:center; color:var(--text-3); padding:40px 0; width:100%; }
    .status-legend { display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin:2px 0 12px; }
    .status-legend-item { display:inline-flex; align-items:center; gap:6px; color:var(--text-2); font-size:11px; }
    .status-legend-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }

    .data-table { width:100%; border-collapse:collapse; font-size:12px; }
    .data-table th { padding:9px 12px; text-align:left; font-size:11px; font-weight:600; color:var(--text-2); text-transform:uppercase; letter-spacing:.4px; background:#f8f9fb; border-bottom:2px solid var(--border); white-space:nowrap; }
    .data-table td { padding:9px 12px; border-bottom:1px solid var(--border); color:var(--text-1); vertical-align:top; }
    .data-table tr:last-child td { border-bottom:none; }
    .badge { display:inline-flex; align-items:center; padding:2px 8px; border-radius:99px; font-size:11px; font-weight:600; }
    .badge-critical { background:#fee2e2; color:#b91c1c; }
    .badge-error { background:#ffedd5; color:#c2410c; }
    .badge-warning { background:#fef9c3; color:#854d0e; }
    .badge-info { background:#e0f2fe; color:#075985; }
    .badge-default { background:#f0f2f5; color:var(--text-2); }
    .mono { font-family: 'Menlo','Consolas',monospace; font-size:11px; }
    .empty { padding:40px 0; text-align:center; color:var(--text-3); font-size:13px; }
    .pagination { display:flex; align-items:center; gap:4px; padding:12px 18px; border-top:1px solid var(--border); }
    .pagination .page-info { font-size:12px; color:var(--text-2); margin-right:auto; }
    .pg-btn { display:inline-flex; align-items:center; justify-content:center; min-width:30px; height:28px; padding:0 8px; border-radius:5px; border:1px solid var(--border); background:var(--surface); font-size:12px; font-weight:500; color:var(--text-1); cursor:pointer; }
    .pg-btn.active { background:var(--accent); color:#fff; border-color:var(--accent); }

    .sparkline-wrap { width:100%; margin:0; min-height:0; }
    .sparkline-svg { display:block; width:100%; height:auto; }
  </style>
</head>
<body>

<nav class="nav">
  <a class="nav-logo" href="#">
    <img src="${escapeHtml(deps.APP_LOGO_URL)}" alt="Axios logo" />
    Axios
  </a>
  <div class="nav-divider"></div>
  <span class="nav-title">Reporting Validation</span>
  <div class="nav-spacer"></div>
  <span class="nav-meta">Pack: <strong style="color:#fff">${escapeHtml(packLabel)}</strong></span>
  <div class="nav-divider"></div>
  <span class="nav-meta">${escapeHtml(nowStr)}</span>
  <span class="nav-badge">Previous: ${escapeHtml(previousVersionLabel)}</span>
  <span class="nav-badge">${exportRows.length} failure rows</span>
</nav>

<div class="page">
  <div class="page-header">
    <div>
      <h1>Validation Results</h1>
      <p>Overview of validation testing for the selected pack — review failures by test, field and submission.</p>
    </div>
  </div>

  <div class="stat-grid">
    ${kpis.map((k)=>{
      const accent = getKpiAccent(k);
      const sub = getKpiSub(k);
      const delta = k?.delta || null;
      const deltaHtml = delta
        ? `<div class="stat-delta ${escapeHtml(delta.tone || 'neutral')}">${escapeHtml(delta.label || 'No change')} vs previous run</div>`
        : `<div class="stat-delta neutral">No previous run comparison</div>`;
      return `<div class="stat-card ${accent}"><div class="stat-label">${escapeHtml(k.title)}</div><div class="stat-value">${escapeHtml(k.value)}</div><div class="stat-sub">${sub}</div>${deltaHtml}</div>`;
    }).join('')}
  </div>

  <div class="panel" id="bar-panel" style="margin-bottom:16px">
    <div class="panel-header">
      <div>
        <div class="panel-title">Top Failure Breakdown</div>
        <div class="panel-subtitle">Top 10 by failure count on a test, field and submission level (broken down by severity)</div>
      </div>
      <div style="display:flex; align-items:center; gap:12px;">
        <div class="tab-group" id="bar-controls"></div>
        <button class="panel-collapse-btn" data-panel="bar" title="Collapse/expand" aria-label="Collapse panel">−</button>
      </div>
    </div>
    <div class="panel-body"><div class="chart-wrap" id="bar-container"></div></div>
  </div>

  <div class="panel" id="trend-panel" style="margin-bottom:16px">
    <div class="panel-header">
      <div><div class="panel-title">Historic Report Performance</div><div class="panel-subtitle">The test, submission and field pass rate over time for saved report versions associated with the current test pack</div></div>
      <button class="panel-collapse-btn" data-panel="trend" title="Collapse/expand" aria-label="Collapse panel">−</button>
    </div>
    <div class="panel-body" style="padding:0 0 2px;"><div class="sparkline-wrap" id="trend-chart"></div></div>
  </div>

  <div class="panel" id="exception-analytics-panel" style="margin-bottom:16px">
    <div class="panel-header">
      <div>
        <div class="panel-title">Exception Management Analysis</div>
        <div class="panel-subtitle">Count of exception tags applied to data points by exception for your organisation</div>
      </div>
      <button class="panel-collapse-btn" data-panel="exception-analytics" title="Collapse/expand" aria-label="Collapse panel">−</button>
    </div>
    <div class="panel-body">
      <div class="chart-wrap" id="exception-analytics-chart"></div>
      <div class="pagination" id="exception-analytics-pagination"></div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <div>
        <div class="panel-title">Failure Detail</div>
        <div class="panel-subtitle">Complete failure analysis for full transparency into each validation failure</div>
      </div>
      <div style="display:flex; align-items:center; gap:12px;">
        <span style="font-size:12px;color:var(--text-3)">${exportRows.length} rows</span>
        <button class="panel-collapse-btn" data-panel="failure" title="Collapse/expand" aria-label="Collapse panel">−</button>
      </div>
    </div>
    <div class="panel-body" style="padding:0;overflow-x:auto;">
      ${exportRows.length === 0 ? '<div class="empty">No failures recorded.</div>' : `
      <table class="data-table" id="failure-table">
        <thead><tr>
          <th>UMR</th>
          <th>Test ID</th>
          <th>Field</th>
          <th>Severity</th>
          <th>Exception ID</th>
          <th>Description</th>
        </tr></thead>
        <tbody id="failure-tbody"></tbody>
      </table>
      <div class="pagination" id="pagination"></div>
      `}
    </div>
  </div>
</div>

<script>
(function(){
  const datasets = ${datasetsJson};
  const trendRows = ${trendJson};
  const config = ${configJson};
  const labels = { test: 'Test', trade: 'Field', umr: 'Submission' };
  const allRows = ${allRowsJson};

  function renderTrendChart() {
    const container = document.getElementById('trend-chart');
    const panel = document.getElementById('trend-panel');
    if (!container) return;
    const rows = (trendRows || [])
      .map((row) => ({
        date: new Date(row.created_at || row.updated_at || Date.now()),
        testPassedPct: Number(row.test_passed_pct),
        submissionsPassedPct: Number.isFinite(Number(row.submissions_failed_pct)) ? (100 - Number(row.submissions_failed_pct)) : Number.NaN,
        fieldsPassedPct: Number.isFinite(Number(row.fields_failed_pct)) ? (100 - Number(row.fields_failed_pct)) : Number.NaN,
        versionName: String(row.version_name || '').trim(),
        workbook: String(row.workbook_name || ''),
        sheet: String(row.sheet_name || ''),
        isCurrent: Boolean(row.is_current),
      }))
      .filter((row) => {
        const hasAnyMetric = Number.isFinite(row.testPassedPct) || Number.isFinite(row.submissionsPassedPct) || Number.isFinite(row.fieldsPassedPct);
        return hasAnyMetric && row.date instanceof Date && !Number.isNaN(row.date.getTime());
      })
      .sort((a, b) => a.date.getTime() - b.date.getTime());

    if (rows.length <= 2) {
      if (panel) panel.style.display = 'none';
      return;
    }

    if (panel) panel.style.display = '';

    const visibleRows = rows.slice().sort((a, b) => b.date.getTime() - a.date.getTime()).slice(0, 5).sort((a, b) => a.date.getTime() - b.date.getTime());
    if (!visibleRows.length) {
      container.innerHTML = '<div class="sparkline-empty">No saved historical pass-rate data available.</div>';
      return;
    }

    const width = 1200;
    const height = 320;
    const pad = { top: 40, right: 40, bottom: 64, left: 60 };
    const pointCount = visibleRows.length;
    const xSpan = Math.max(1, width - pad.left - pad.right);
    const xForIndex = (index) => pointCount <= 1 ? pad.left + (xSpan / 2) : pad.left + ((index / (pointCount - 1)) * xSpan);
    const xFor = (row) => xForIndex(visibleRows.indexOf(row));
    const yFor = (value) => pad.top + ((100 - value) / 100) * (height - pad.top - pad.bottom);
    const escapeSvgText = (value) => String(value || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    const buildSeriesRows = (metricKey) => visibleRows.filter((row) => Number.isFinite(row[metricKey]));
    const buildSeriesPoints = (metricKey) => buildSeriesRows(metricKey).map((row) => xFor(row).toFixed(2) + ',' + yFor(row[metricKey]).toFixed(2)).join(' ');

    const testPoints = buildSeriesPoints('testPassedPct');
    const submissionPoints = buildSeriesPoints('submissionsPassedPct');
    const fieldPoints = buildSeriesPoints('fieldsPassedPct');

    const yTicks = [0, 25, 50, 75, 100];
    const tickLines = yTicks.map((tick) => {
      const y = yFor(tick).toFixed(2);
      return '<line x1="' + pad.left + '" y1="' + y + '" x2="' + (width - pad.right) + '" y2="' + y + '" stroke="#eef1f5" />' +
        '<text x="' + (pad.left - 8) + '" y="' + (Number(y) + 4) + '" text-anchor="end" fill="#8a92a6" font-size="10">' + tick + '%</text>';
    }).join('');

    const verticalLines = visibleRows.map((row, index) => {
      const x = xForIndex(index).toFixed(2);
      return '<line x1="' + x + '" y1="' + pad.top + '" x2="' + x + '" y2="' + (height - pad.bottom) + '" stroke="#f1f5f9" />';
    }).join('');

    const xAxisLabels = visibleRows.map((row, index) => {
      const x = xForIndex(index).toFixed(2);
      const rawLabel = String(row.versionName || ('Version ' + (index + 1))).trim();
      const shortLabel = rawLabel.length > 14 ? (rawLabel.slice(0, 13) + '…') : rawLabel;
      return '<text x="' + x + '" y="' + (height - pad.bottom + 26) + '" text-anchor="middle" fill="#8a92a6" font-size="10"><title>' + escapeSvgText(rawLabel) + '</title>' + escapeSvgText(shortLabel) + '</text>';
    }).join('');

    const buildCircles = (metricKey, color, seriesLabel) => buildSeriesRows(metricKey).map((row) => {
      const x = xFor(row).toFixed(2);
      const y = yFor(row[metricKey]).toFixed(2);
      const versionLabel = row.versionName || 'Unnamed version';
      const tip = (seriesLabel + ' • ' + versionLabel + ' • ' + row.date.toLocaleString('en-GB') + ' • ' + row[metricKey].toFixed(1) + '% • ' + row.workbook + ' / ' + row.sheet).replace(/"/g, '&quot;');
      const radius = row.isCurrent ? '5' : '3.5';
      const fill = row.isCurrent ? '#6b7280' : color;
      return '<circle cx="' + x + '" cy="' + y + '" r="' + radius + '" fill="' + fill + '"><title>' + tip + '</title></circle>';
    }).join('');

    const circles = [
      buildCircles('testPassedPct', '#4f6ef7', 'Tests passed %'),
      buildCircles('submissionsPassedPct', '#ef4444', 'Submissions passed %'),
      buildCircles('fieldsPassedPct', '#f59e0b', 'Fields passed %'),
    ].join('');

    const linePaths = [
      testPoints ? '<polyline fill="none" stroke="#4f6ef7" stroke-width="2.5" points="' + testPoints + '" />' : '',
      submissionPoints ? '<polyline fill="none" stroke="#ef4444" stroke-width="2.2" points="' + submissionPoints + '" />' : '',
      fieldPoints ? '<polyline fill="none" stroke="#f59e0b" stroke-width="2.2" points="' + fieldPoints + '" />' : '',
    ].join('');

    const legend =
      '<g transform="translate(20,0)">' +
        '<line x1="8" y1="14" x2="28" y2="14" stroke="#4f6ef7" stroke-width="2.5" />' +
        '<text x="32" y="17" fill="#5a6072" font-size="10">Tests passed %</text>' +
        '<line x1="130" y1="14" x2="150" y2="14" stroke="#ef4444" stroke-width="2.2" />' +
        '<text x="154" y="17" fill="#5a6072" font-size="10">Submissions passed %</text>' +
        '<line x1="300" y1="14" x2="320" y2="14" stroke="#f59e0b" stroke-width="2.2" />' +
        '<text x="324" y="17" fill="#5a6072" font-size="10">Fields passed %</text>' +
      '</g>';

    container.innerHTML =
      '<svg class="sparkline-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Pass percentages over time">' +
        legend + verticalLines + tickLines + linePaths + circles + xAxisLabels +
      '</svg>';
  }

  function renderBars(key) {
    const rows = datasets[key] || [];
    const container = document.getElementById('bar-container');
    container.innerHTML = '';
    if (!rows.length) {
      container.innerHTML = '<div class="empty">No data available for this view.</div>';
      return;
    }
    const max = Math.max(...rows.map((r) => r.total), 1);

    const legend = document.createElement('div');
    legend.className = 'severity-legend';
    legend.innerHTML =
      '<span class="severity-legend-item"><span class="severity-dot warn"></span>Warning</span>' +
      '<span class="severity-legend-item"><span class="severity-dot error"></span>Error</span>' +
      '<span class="severity-legend-item"><span class="severity-dot critical"></span>Critical</span>';
    container.appendChild(legend);

    rows.forEach((r) => {
      const total = Number(r.total || 0);
      const barPct = max ? (total / max) * 100 : 0;
      const warningPct = total ? ((r.WARNING || 0) / total) * 100 : 0;
      const errorPct = total ? ((r.ERROR || 0) / total) * 100 : 0;
      const criticalPct = total ? ((r.CRITICAL || 0) / total) * 100 : 0;
      const row = document.createElement('div');
      row.className = 'bar-row';
      row.innerHTML =
        '<div class="bar-label" title="' + String(r.label || '').replace(/"/g,'&quot;') + '">' + String(r.label || '') + '</div>' +
        '<div class="bar-track"><div class="bar-fill" style="width:' + barPct + '%">' +
          '<div class="bar-seg warn" style="width:' + warningPct + '%" title="Warning: ' + (r.WARNING || 0) + '"></div>' +
          '<div class="bar-seg error" style="width:' + errorPct + '%" title="Error: ' + (r.ERROR || 0) + '"></div>' +
          '<div class="bar-seg critical" style="width:' + criticalPct + '%" title="Critical: ' + (r.CRITICAL || 0) + '"></div>' +
        '</div></div>' +
        '<div class="bar-count">' + total + '</div>';
      container.appendChild(row);
    });
  }

  function setupControls() {
    const controls = document.getElementById('bar-controls');
    if (!controls) return;
    controls.innerHTML = '';
    Object.entries(labels).forEach(([k, label], i) => {
      const btn = document.createElement('button');
      btn.className = 'tab-btn' + (i === 0 ? ' active' : '');
      btn.textContent = label;
      btn.dataset.key = k;
      btn.addEventListener('click', () => {
        document.querySelectorAll('#bar-controls .tab-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        renderBars(k);
      });
      controls.appendChild(btn);
    });
    renderBars('test');
  }

  const EXCEPTION_ANALYTICS_PAGE_SIZE = 10;
  let exceptionAnalyticsData = [];
  let exceptionAnalyticsCurrentPage = 1;

  const EXCEPTION_STATUS_STYLES = {
    'to do': { color: '#cbd5e1', label: 'To Do' },
    'in progress': { color: '#93c5fd', label: 'In Progress' },
    'in review': { color: '#a78bfa', label: 'In Review' },
    blocked: { color: '#fca5a5', label: 'Blocked' },
    complete: { color: '#86efac', label: 'Complete' },
    default: { color: '#7aa3d9', label: 'Other' },
  };

  function normalizeExceptionStatus(status) {
    return String(status || '').trim().toLowerCase();
  }

  function getExceptionStatusStyle(status) {
    const normalizedStatus = normalizeExceptionStatus(status);
    return EXCEPTION_STATUS_STYLES[normalizedStatus] || EXCEPTION_STATUS_STYLES.default;
  }

  function renderExceptionStatusLegend(container) {
    const statusesInData = new Set((exceptionAnalyticsData || []).map((item) => normalizeExceptionStatus(item.status)).filter(Boolean));
    const statusOrder = ['to do', 'in progress', 'in review', 'blocked', 'complete'];
    const orderedStatuses = statusOrder.filter((status) => statusesInData.has(status));
    const unknownStatuses = Array.from(statusesInData).filter((status) => !statusOrder.includes(status));
    const legendStatuses = orderedStatuses.concat(unknownStatuses);

    if (!legendStatuses.length) {
      return;
    }

    const legend = document.createElement('div');
    legend.className = 'status-legend';

    legendStatuses.forEach((status) => {
      const style = getExceptionStatusStyle(status);
      const item = document.createElement('span');
      item.className = 'status-legend-item';
      item.innerHTML =
        '<span class="status-legend-dot" style="background:' + style.color + '"></span>' +
        '<span>' + (EXCEPTION_STATUS_STYLES[status]?.label || status || EXCEPTION_STATUS_STYLES.default.label) + '</span>';
      legend.appendChild(item);
    });

    container.appendChild(legend);
  }

  function renderExceptionAnalyticsChart() {
    const container = document.getElementById('exception-analytics-chart');
    const panel = document.getElementById('exception-analytics-panel');
    if (!container) {
      return;
    }

    if (!Array.isArray(exceptionAnalyticsData) || exceptionAnalyticsData.length === 0) {
      if (panel) panel.style.display = '';
      container.innerHTML = '<div class="vertical-chart-empty">No exceptions have been created for your organisation yet.</div>';

      const paginationDiv = document.getElementById('exception-analytics-pagination');
      if (paginationDiv) paginationDiv.innerHTML = '';
      return;
    }

    if (panel) panel.style.display = '';

    const totalPages = Math.ceil(exceptionAnalyticsData.length / EXCEPTION_ANALYTICS_PAGE_SIZE);
    const start = (exceptionAnalyticsCurrentPage - 1) * EXCEPTION_ANALYTICS_PAGE_SIZE;
    const end = start + EXCEPTION_ANALYTICS_PAGE_SIZE;
    const pageData = exceptionAnalyticsData.slice(start, end);

    if (!pageData.length) {
      container.innerHTML = '';
      return;
    }

    const maxCount = Math.max(...exceptionAnalyticsData.map((item) => item.tag_count), 1);
    const chartHeight = 200;

    container.innerHTML = '';
    renderExceptionStatusLegend(container);

    const chartWrap = document.createElement('div');
    chartWrap.className = 'vertical-chart-wrap';

    pageData.forEach((item) => {
      const count = Number(item.tag_count || 0);
      const barHeight = count > 0 ? (count / maxCount) * chartHeight : 2;

      const barContainer = document.createElement('div');
      barContainer.className = 'vertical-bar-container';

      const valueLabel = document.createElement('div');
      valueLabel.className = 'vertical-bar-value';
      valueLabel.textContent = count;

      const barTrack = document.createElement('div');
      barTrack.className = 'vertical-bar-track';
      barTrack.style.height = chartHeight + 'px';

      const barFill = document.createElement('div');
      barFill.className = 'vertical-bar-fill';
      barFill.style.height = barHeight + 'px';
      barFill.style.background = getExceptionStatusStyle(item.status).color;

      barTrack.appendChild(barFill);

      const barLabel = document.createElement('div');
      barLabel.className = 'vertical-bar-label';
      barLabel.title = item.exception_id;
      barLabel.textContent = item.exception_id.length > 12 ? item.exception_id.substring(0, 10) + '...' : item.exception_id;

      barContainer.appendChild(valueLabel);
      barContainer.appendChild(barTrack);
      barContainer.appendChild(barLabel);
      chartWrap.appendChild(barContainer);
    });

    container.appendChild(chartWrap);
    renderExceptionAnalyticsPagination(totalPages);
  }

  function renderExceptionAnalyticsPagination(totalPages) {
    const paginationDiv = document.getElementById('exception-analytics-pagination');
    if (!paginationDiv) return;

    const currentPage = exceptionAnalyticsCurrentPage;
    const start = (currentPage - 1) * EXCEPTION_ANALYTICS_PAGE_SIZE + 1;
    const end = Math.min(currentPage * EXCEPTION_ANALYTICS_PAGE_SIZE, exceptionAnalyticsData.length);

    let html = '<span class="page-info">Showing ' + start + '–' + end + ' of ' + exceptionAnalyticsData.length + ' exceptions</span>';
    html += '<button class="pg-btn" id="exc-pg-prev"' + (currentPage <= 1 ? ' disabled' : '') + '>&lsaquo; Prev</button>';

    const pages = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      pages.push(1);
      if (currentPage > 3) pages.push('...');
      for (let i = Math.max(2, currentPage - 1); i <= Math.min(totalPages - 1, currentPage + 1); i++) pages.push(i);
      if (currentPage < totalPages - 2) pages.push('...');
      pages.push(totalPages);
    }

    pages.forEach((p) => {
      if (p === '...') {
        html += '<span class="pg-btn" style="border:none;background:none;cursor:default">…</span>';
      } else {
        html += '<button class="pg-btn' + (p === currentPage ? ' active' : '') + '" data-exc-page="' + p + '">' + p + '</button>';
      }
    });

    html += '<button class="pg-btn" id="exc-pg-next"' + (currentPage >= totalPages ? ' disabled' : '') + '>Next &rsaquo;</button>';

    paginationDiv.innerHTML = html;

    paginationDiv.querySelectorAll('[data-exc-page]').forEach((btn) => {
      btn.addEventListener('click', () => {
        exceptionAnalyticsCurrentPage = parseInt(btn.dataset.excPage, 10);
        renderExceptionAnalyticsChart();
      });
    });

    const prevBtn = paginationDiv.querySelector('#exc-pg-prev');
    const nextBtn = paginationDiv.querySelector('#exc-pg-next');

    if (prevBtn) {
      prevBtn.addEventListener('click', () => {
        if (exceptionAnalyticsCurrentPage > 1) {
          exceptionAnalyticsCurrentPage -= 1;
          renderExceptionAnalyticsChart();
        }
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener('click', () => {
        if (exceptionAnalyticsCurrentPage < totalPages) {
          exceptionAnalyticsCurrentPage += 1;
          renderExceptionAnalyticsChart();
        }
      });
    }
  }

  async function fetchExceptionAnalytics() {
    try {
      if (!config || !config.backendUrl || !config.userEmail) {
        exceptionAnalyticsData = [];
        renderExceptionAnalyticsChart();
        return;
      }

      const response = await fetch(config.backendUrl + '/api/v1/exceptions/analytics', {
        method: 'GET',
        headers: {
          'X-Excel-User-Email': config.userEmail,
        },
        cache: 'no-store',
      });

      if (!response.ok) {
        exceptionAnalyticsData = [];
        renderExceptionAnalyticsChart();
        return;
      }

      const payload = await response.json().catch(() => ({ analytics: [] }));
      exceptionAnalyticsData = Array.isArray(payload?.analytics) ? payload.analytics : [];
      exceptionAnalyticsData.sort((a, b) => (b.tag_count || 0) - (a.tag_count || 0));

      exceptionAnalyticsCurrentPage = 1;
      renderExceptionAnalyticsChart();
    } catch {
      exceptionAnalyticsData = [];
      renderExceptionAnalyticsChart();
    }
  }

  const PAGE_SIZE = 10;
  let currentPage = 1;
  const totalPages = () => Math.max(1, Math.ceil(allRows.length / PAGE_SIZE));

  function escHtml(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function renderTable(page) {
    const tbody = document.getElementById('failure-tbody');
    if (!tbody) return;
    const start = (page - 1) * PAGE_SIZE;
    const slice = allRows.slice(start, start + PAGE_SIZE);
    tbody.innerHTML = slice.map((r) => {
      const sev = String(r.severity || '').toUpperCase();
      const bc = sev === 'CRITICAL' ? 'badge-critical' : sev === 'ERROR' ? 'badge-error' : sev === 'WARNING' ? 'badge-warning' : sev === 'INFO' ? 'badge-info' : 'badge-default';
      return '<tr>' +
        '<td class="mono">' + escHtml(r.umr || '\u2014') + '</td>' +
        '<td class="mono">' + escHtml(r.testId || '\u2014') + '</td>' +
        '<td>' + escHtml(r.fieldName || '\u2014') + '</td>' +
        '<td>' + (sev ? '<span class="badge ' + bc + '">' + escHtml(sev) + '</span>' : '\u2014') + '</td>' +
        '<td class="mono">' + escHtml(r.exceptionId || '\u2014') + '</td>' +
        '<td style="max-width:400px;white-space:pre-wrap;word-break:break-word">' + escHtml(r.description || '\u2014') + '</td>' +
        '</tr>';
    }).join('');
  }

  function renderPagination(page) {
    const pg = document.getElementById('pagination');
    if (!pg) return;
    const tp = totalPages();
    const start = (page - 1) * PAGE_SIZE + 1;
    const end = Math.min(page * PAGE_SIZE, allRows.length);
    let html = '<span class="page-info">Showing ' + start + '–' + end + ' of ' + allRows.length + ' rows</span>';

    html += '<button class="pg-btn" id="pg-prev"' + (page <= 1 ? ' disabled' : '') + '>&lsaquo; Prev</button>';

    const pages = [];
    if (tp <= 7) {
      for (let i = 1; i <= tp; i++) pages.push(i);
    } else {
      pages.push(1);
      if (page > 3) pages.push('...');
      for (let i = Math.max(2, page - 1); i <= Math.min(tp - 1, page + 1); i++) pages.push(i);
      if (page < tp - 2) pages.push('...');
      pages.push(tp);
    }
    pages.forEach((p) => {
      if (p === '...') {
        html += '<span class="pg-btn" style="border:none;background:none;cursor:default">…</span>';
      } else {
        html += '<button class="pg-btn' + (p === page ? ' active' : '') + '" data-page="' + p + '">' + p + '</button>';
      }
    });

    html += '<button class="pg-btn" id="pg-next"' + (page >= tp ? ' disabled' : '') + '>Next &rsaquo;</button>';

    pg.innerHTML = html;

    pg.querySelectorAll('[data-page]').forEach((btn) => {
      btn.addEventListener('click', () => { currentPage = parseInt(btn.dataset.page, 10); renderTable(currentPage); renderPagination(currentPage); });
    });
    const prev = pg.querySelector('#pg-prev');
    const next = pg.querySelector('#pg-next');
    if (prev) prev.addEventListener('click', () => { if (currentPage > 1) { currentPage -= 1; renderTable(currentPage); renderPagination(currentPage); } });
    if (next) next.addEventListener('click', () => { if (currentPage < totalPages()) { currentPage += 1; renderTable(currentPage); renderPagination(currentPage); } });
  }

  function setupTable() {
    if (!document.getElementById('failure-tbody')) return;
    renderTable(1);
    renderPagination(1);
  }

  function setupPanelCollapse() {
    const panels = document.querySelectorAll('.panel-header');
    panels.forEach((header) => {
      header.addEventListener('click', (e) => {
        if (e.target.closest('.tab-group') || e.target.closest('.tab-btn')) return;

        const panel = header.closest('.panel');
        const body = panel.querySelector('.panel-body');
        const btn = header.querySelector('.panel-collapse-btn');

        if (!body) return;

        body.classList.toggle('collapsed');
        if (btn) {
          btn.classList.toggle('collapsed');
          const isCollapsed = body.classList.contains('collapsed');
          btn.textContent = isCollapsed ? '+' : '−';
          btn.setAttribute('aria-label', isCollapsed ? 'Expand panel' : 'Collapse panel');
        }
      });
    });

    const collapseButtons = document.querySelectorAll('.panel-collapse-btn');
    collapseButtons.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const panel = btn.closest('.panel');
        const body = panel.querySelector('.panel-body');

        if (!body) return;

        body.classList.toggle('collapsed');
        btn.classList.toggle('collapsed');
        const isCollapsed = body.classList.contains('collapsed');
        btn.textContent = isCollapsed ? '+' : '−';
        btn.setAttribute('aria-label', isCollapsed ? 'Expand panel' : 'Collapse panel');
      });
    });
  }

  let initialized = false;
  function init() {
    if (initialized) return;
    initialized = true;
    renderTrendChart();
    setupControls();
    setupTable();
    fetchExceptionAnalytics();
    setupPanelCollapse();
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(init, 0);
  } else {
    document.addEventListener('DOMContentLoaded', init, { once: true });
    window.addEventListener('load', init, { once: true });
  }
})();
</script>
</body>
</html>`;

      win.document.open();
      win.document.write(html);
      win.document.close();

      deps.setStatus(`Visualisation opened in new tab: ${exportRows.length} failure rows.`);
    } catch (error) {
      deps.setStatus(`Visualise failed: ${error?.message || "Unexpected error"}`, true);
    } finally {
      if (visualiseButton) {
        visualiseButton.disabled = false;
      }
    }
  }

  global.TaskpaneVisualisation = {
    computeVisualisationKpisFromCurrentRun,
    visualiseValidationResults,
  };
}(window));
