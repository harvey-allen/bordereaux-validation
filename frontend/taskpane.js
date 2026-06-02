/**
 * Heatmap color gradient: no failures=white, then level 1-10 as light→dark red.
 * Uses severity score instead of simple failure count for more nuanced coloring.
 * Severity levels: INFO=0, WARNING=1, ERROR=2, CRITICAL=3
 */
const DEFAULT_EXCEL_EMAIL = "harveyallen2001@gmail.com";
let packConfigsByPack = {};
let currentPackSelection = null;
let territoriesByPack = {};
let lastValidationResults = [];
let lastValidationSourceSheetName = null;
let lastValidationExecutedTests = [];
let lastValidationPack = null;

const DEFAULT_PACK_OPTIONS = [
  { value: "risk_and_premium", label: "Risk and Premium" },
  { value: "claims", label: "Claims" },
  { value: "csrd", label: "CSRD" },
  { value: "tcfd", label: "TCFD" },
];

const SUSTAINABILITY_PACKS = new Set(["csrd", "tcfd"]);

function formatPackLabel(packName) {
  const normalized = String(packName || "").trim();
  if (!normalized) {
    return "";
  }
  return normalized
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getDefaultPackValues() {
  return DEFAULT_PACK_OPTIONS.map((pack) => pack.value);
}

function getPackLabel(packName) {
  const normalized = String(packName || "").trim().toLowerCase();
  const known = DEFAULT_PACK_OPTIONS.find((pack) => pack.value === normalized);
  return known?.label || formatPackLabel(normalized);
}

function populatePackSelect(packValues) {
  const select = document.getElementById("testPacks");
  if (!select) {
    return [];
  }

  const normalizedValues = Array.from(new Set(
    (Array.isArray(packValues) ? packValues : [])
      .map((value) => String(value || "").trim().toLowerCase())
      .filter(Boolean)
  ));

  const valuesToRender = normalizedValues.length > 0 ? normalizedValues : getDefaultPackValues();

  select.innerHTML = "";
  for (const packName of valuesToRender) {
    const option = document.createElement("option");
    option.value = packName;
    option.textContent = getPackLabel(packName);
    select.appendChild(option);
  }

  return valuesToRender;
}

async function loadSubscribedPackValues(excelUserEmail) {
  try {
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/test-packs`, {
      method: "GET",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return getDefaultPackValues();
    }

    const payload = await response.json().catch(() => ({}));
    const allowedPacks = Array.isArray(payload?.allowed_packs)
      ? payload.allowed_packs
      : (Array.isArray(payload?.all_packs) ? payload.all_packs : []);

    const normalized = Array.from(new Set(
      allowedPacks
        .map((value) => String(value || "").trim().toLowerCase())
        .filter(Boolean)
    ));

    return normalized.length > 0 ? normalized : getDefaultPackValues();
  } catch {
    return getDefaultPackValues();
  }
}

function updateActionButtons() {
  const extractButton = document.getElementById("extractResults");
  const visualiseButton = document.getElementById("visualiseResults");
  const hasResults = Array.isArray(lastValidationResults) && lastValidationResults.length > 0;
  if (extractButton) extractButton.disabled = !hasResults;
  if (visualiseButton) visualiseButton.disabled = !hasResults;
}

// Build sankey summarising: Total Tests -> Passed/Failed -> Severity (failed) -> Test Type
async function buildSankeyPngBase64(exportRows) {
  // Aggregate distinct failed tests
  const failedTestInfo = new Map(); // testId -> { severities: Set, types: Set }
  for (const r of exportRows) {
    const testId = String(r.testId || "(unknown)").trim();
    const severity = String((r.severity || "ERROR")).toUpperCase();
    const testType = String(r.testType || "(unknown)");
    if (!failedTestInfo.has(testId)) failedTestInfo.set(testId, { severities: new Set(), types: new Set() });
    const info = failedTestInfo.get(testId);
    info.severities.add(severity);
    if (testType) info.types.add(testType);
  }

  const failedDistinctCount = failedTestInfo.size;
  const totalTests = Array.isArray(lastValidationExecutedTests) && lastValidationExecutedTests.length > 0
    ? lastValidationExecutedTests.length
    : failedDistinctCount;
  const passedCount = Math.max(0, totalTests - failedDistinctCount);

  // Determine highest severity per failed test (CRITICAL>ERROR>WARNING>INFO)
  const severityOrder = ["INFO", "WARNING", "ERROR", "CRITICAL"];
  const severityRank = Object.fromEntries(severityOrder.map((s, i) => [s, i]));

  const severityBuckets = new Map(); // severity -> Set(testId)
  const severityTypeBuckets = new Map(); // severity -> Map(type -> Set(testId))

  for (const [testId, info] of failedTestInfo.entries()) {
    // pick highest severity seen for this test
    let chosen = "ERROR";
    let bestRank = -1;
    for (const s of info.severities) {
      const r = severityRank[s] ?? -1;
      if (r > bestRank) { bestRank = r; chosen = s; }
    }

    if (!severityBuckets.has(chosen)) severityBuckets.set(chosen, new Set());
    severityBuckets.get(chosen).add(testId);

    if (!severityTypeBuckets.has(chosen)) severityTypeBuckets.set(chosen, new Map());
    const typeMap = severityTypeBuckets.get(chosen);
    const types = Array.from(info.types).length > 0 ? Array.from(info.types) : ["(unknown)"];
    // assign test to first type (deterministic)
    const chosenType = types[0];
    if (!typeMap.has(chosenType)) typeMap.set(chosenType, new Set());
    typeMap.get(chosenType).add(testId);
  }

  // Build node list and links
  const nodes = [];
  const links = [];
  const addNode = (name) => {
    const idx = nodes.findIndex(n => n.name === name);
    if (idx >= 0) return idx;
    nodes.push({ name });
    return nodes.length - 1;
  };

  const allTestsNode = addNode('All Tests');
  const totalNode = addNode('Total Tests');
  const passedNode = addNode('Passed Tests');
  const failedNode = addNode('Failed Tests');
  links.push({ source: allTestsNode, target: totalNode, value: totalTests });
  links.push({ source: totalNode, target: passedNode, value: passedCount });
  links.push({ source: totalNode, target: failedNode, value: failedDistinctCount });

  // Failed -> severity
  for (const [severity, setOfTests] of severityBuckets.entries()) {
    const sevNode = addNode(severity);
    links.push({ source: failedNode, target: sevNode, value: setOfTests.size });

    // severity -> test type
    const typeMap = severityTypeBuckets.get(severity) || new Map();
    for (const [typeName, testsSet] of typeMap.entries()) {
      const typeNode = addNode(String(typeName));
      links.push({ source: sevNode, target: typeNode, value: testsSet.size });
    }
  }

  // Create an offscreen SVG using D3 (stretched wider for Sankey)
  const width = 1800;
  const height = 330;
  const svg = d3.create('svg')
    .attr('xmlns', 'http://www.w3.org/2000/svg')
    .attr('width', width)
    .attr('height', height)
    .style('font-family', 'sans-serif');

  const sankeyGenerator = d3.sankey()
    .nodeWidth(22)
    .nodePadding(16)
    .extent([[1, 1], [width - 1, height - 6]]);

  const graph = sankeyGenerator({ nodes: nodes.map(d => Object.assign({}, d)), links: links.map(d => Object.assign({}, d)) });

  // Colour mapping requested: pass (light green), fail (light red), warning (yellow), error (orange), critical (red)
  const COLOR = {
    ALL: '#e5e7eb',
    PASS: '#c8f7d4', // light green
    FAIL: '#ffd6d6', // light red
    INFO: '#d9d9d9',
    WARNING: '#ffd966',
    ERROR: '#ffb74d',
    CRITICAL: '#ff4d4d',
    DEFAULT: '#0f6cbd',
    LINK_DEFAULT: '#7aa3d9',
  };

  const TEST_TYPE_COLOR = {
    LOGIC: '#60a5fa',   // blue
    QUALITY: '#a78bfa', // purple
    MISSING: '#f9a8d4', // pink
    LOOKUP: '#93c5fd',  // light blue
    OTHER: '#d1d5db',   // grey
  };

  const getTestTypeColor = (name) => {
    const key = String(name || '').trim().toUpperCase();
    return TEST_TYPE_COLOR[key] || null;
  };

  // Helper to choose text colour (black on light backgrounds, white on dark)
  function textColorFor(hex) {
    try {
      const c = hex.replace('#', '');
      const r = parseInt(c.substring(0,2),16);
      const g = parseInt(c.substring(2,4),16);
      const b = parseInt(c.substring(4,6),16);
      const luminance = (0.2126*r + 0.7152*g + 0.0722*b) / 255;
      return luminance > 0.6 ? '#000000' : '#ffffff';
    } catch { return '#ffffff'; }
  }

  // Build a map of node name -> colour
  const nodeColourMap = new Map();
  nodeColourMap.set('All Tests', COLOR.ALL);
  nodeColourMap.set('Passed Tests', COLOR.PASS);
  nodeColourMap.set('Failed Tests', COLOR.FAIL);
  nodeColourMap.set('Total Tests', COLOR.DEFAULT);
  // Map severities
  nodeColourMap.set('INFO', COLOR.INFO);
  nodeColourMap.set('WARNING', COLOR.WARNING);
  nodeColourMap.set('ERROR', COLOR.ERROR);
  nodeColourMap.set('CRITICAL', COLOR.CRITICAL);

  // Draw links and nodes with colours derived from their target or role
  svg.append('g')
    .attr('fill', 'none')
    .attr('stroke-opacity', 0.7)
    .selectAll('path')
    .data(graph.links)
    .join('path')
    .attr('d', d3.sankeyLinkHorizontal())
    .attr('stroke', d => {
      // Prefer the target node colour where sensible
      const tgt = d.target && d.target.name ? d.target.name : null;
      if (!tgt) return COLOR.LINK_DEFAULT;
      if (tgt === 'Total Tests') return '#cbd5e1';
      if (tgt === 'Passed Tests') return COLOR.PASS;
      if (tgt === 'Failed Tests') return COLOR.FAIL;
      if (tgt === 'WARNING') return COLOR.WARNING;
      if (tgt === 'ERROR') return COLOR.ERROR;
      if (tgt === 'CRITICAL') return COLOR.CRITICAL;
      const testTypeColor = getTestTypeColor(tgt);
      if (testTypeColor) return testTypeColor;
      return COLOR.LINK_DEFAULT;
    })
    .attr('stroke-width', d => Math.max(1, d.width))
    .attr('stroke-linecap', 'butt')
    .attr('stroke-linejoin', 'miter');

  const node = svg.append('g')
    .selectAll('g')
    .data(graph.nodes)
    .join('g');

  node.append('rect')
    .attr('x', d => d.x0)
    .attr('y', d => d.y0)
    .attr('height', d => Math.max(1, d.y1 - d.y0))
    .attr('width', d => Math.max(1, d.x1 - d.x0))
    .attr('fill', d => nodeColourMap.get(d.name) || getTestTypeColor(d.name) || COLOR.DEFAULT)
    .attr('opacity', 0.95);

  node.append('text')
    .attr('x', d => d.name === 'Failed Tests'
      ? (d.x0 + d.x1) / 2
      : (d.x0 < width / 2 ? d.x1 + 8 : d.x0 - 8))
    .attr('y', d => (d.y1 + d.y0) / 2)
    .attr('dy', '0.35em')
    .attr('text-anchor', d => d.name === 'Failed Tests' ? 'middle' : (d.x0 < width / 2 ? 'start' : 'end'))
    .attr('fill', '#000000')
    .style('font-size', '13px')
    .text(d => {
      if (d.name === 'Total Tests') return '';

      // show node label and value where available
      const rawLabel = String(d.name || '');
      const label = rawLabel ? `${rawLabel.charAt(0).toUpperCase()}${rawLabel.slice(1).toLowerCase()}` : '';
      const val = (typeof d.value === 'number' && d.value > 0) ? ` (${d.value})` : '';
      return label + val;
    });

  // Serialize SVG
  const svgString = new XMLSerializer().serializeToString(svg.node());

  // Convert SVG to PNG via canvas
  const img = new Image();
  const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(svgBlob);

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');

  return new Promise((resolve, reject) => {
    img.onload = () => {
      try {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
        const dataUrl = canvas.toDataURL('image/png');
        URL.revokeObjectURL(url);
        const base64 = dataUrl.split(',')[1];
        resolve(base64);
      } catch (e) {
        URL.revokeObjectURL(url);
        reject(e);
      }
    };
    img.onerror = (e) => { URL.revokeObjectURL(url); reject(new Error('Failed to render SVG to image')); };
    img.src = url;
  });
}

async function insertSankeyImageIntoResults(exportRows) {
  try {
    setStatus('Generating Sankey image...');
    const base64Png = await buildSankeyPngBase64(exportRows);
    setStatus('Inserting Sankey into Results sheet...');
    await Excel.run(async (context) => {
      const workbook = context.workbook;
      let sheet = workbook.worksheets.getItemOrNullObject('Results');
      sheet.load('isNullObject');
      await context.sync();
      if (sheet.isNullObject) {
        workbook.worksheets.add('Results');
      }
      const resultsSheet = workbook.worksheets.getItem('Results');

      // Ensure visualisation sheet uses white background and black fonts.
      const usedRange = resultsSheet.getUsedRangeOrNullObject();
      usedRange.load('isNullObject');
      await context.sync();
      if (!usedRange.isNullObject) {
        usedRange.format.fill.color = '#D9D9D9';
        usedRange.format.font.color = '#000000';
      } else {
        // If sheet is empty, apply formatting to a reasonable area
        const fullRange = resultsSheet.getRange('A1:ZZ1000');
        fullRange.format.fill.color = '#D9D9D9';
        fullRange.format.font.color = '#000000';
      }

      // Add image (expects base64 without prefix) and position at cell B20
      const anchor = resultsSheet.getRange('B20');
      anchor.load(['left', 'top']);
      await context.sync();
      try {
        const imgShape = resultsSheet.shapes.addImage(base64Png);
        try { imgShape.left = anchor.left; } catch {}
        try { imgShape.top = anchor.top; } catch {}
        // Set a reasonable display size for the Sankey
        try { imgShape.width = 1250; } catch {}
        try { imgShape.height = 600; } catch {}
      } catch (shErr) {
        // fallback: add image without explicit positioning
        try { resultsSheet.shapes.addImage(base64Png); } catch {}
      }
      await context.sync();
    });
    setStatus('Sankey image inserted into Results sheet.');
  } catch (err) {
    setStatus(`Sankey generation failed: ${err?.message || 'Unknown error'}`, true);
  }
}

function getDefaultPackConfig(selectedPack) {
  const normalizedPack = String(selectedPack || "").trim().toLowerCase();

  const defaultRefByPack = {
    risk_and_premium: "Unique Market Reference (UMR)",
    claims: "Unique Market Reference (UMR)",
    csrd: "Company Identifier",
    tcfd: "Entity Name",
  };

  return {
    testPack: normalizedPack,
    ID: defaultRefByPack[normalizedPack] || "Record ID",
  };
}

function normalizePackConfigShape(config, selectedPack) {
  const normalizedPack = String(selectedPack || "").trim().toLowerCase();
  const next = { ...(config || {}) };
  const fallbackId = getDefaultPackConfig(normalizedPack).ID;

  const resolvedId = String(
    next.ID
      || next.id
      || next.UMR
      || next.UTIColumn
      || fallbackId
      || ""
  ).trim();

  if (resolvedId) {
    next.ID = resolvedId;
  }

  delete next.id;
  delete next.UMR;
  delete next.UTIColumn;

  if (normalizedPack) {
    next.testPack = normalizedPack;
  }

  return next;
}

function heatmapColor(severityScore, maxSeverityScore) {
  const startRed = 255, startGreen = 235, startBlue = 238;
  const endRed = 139, endGreen = 0, endBlue = 0;
  const scaleCap = CONFIG.HEATMAP_FAIL_CAP;

  const _maxSeverityScore = maxSeverityScore;
  void _maxSeverityScore;

  const numericScore = Number(severityScore) || 0;
  if (numericScore <= 0) {
    return "#ffffff";
  }

  const level = Math.max(1, Math.min(scaleCap, Math.floor(numericScore)));
  const ratio = (level - 1) / (scaleCap - 1);

  const red = Math.round(startRed + (endRed - startRed) * ratio);
  const green = Math.round(startGreen + (endGreen - startGreen) * ratio);
  const blue = Math.round(startBlue + (endBlue - startBlue) * ratio);
  return `#${red.toString(16).padStart(2, '0')}${green.toString(16).padStart(2, '0')}${blue.toString(16).padStart(2, '0')}`;
}

function withDefaultEnabledTests(packConfigs, selectedPack) {
  const normalizedPack = String(selectedPack || "").trim().toLowerCase();
  if (!normalizedPack) {
    return packConfigs;
  }

  const nextConfigs = { ...(packConfigs || {}) };
  const existingPackConfig = { ...(nextConfigs[normalizedPack] || {}) };
  const configuredTests = Array.isArray(existingPackConfig.enabledTests)
    ? existingPackConfig.enabledTests
    : [];
  const normalizedEnabledTests = Array.from(
    new Set(
      configuredTests
        .map((item) => String(item || "").trim())
        .filter(Boolean)
        .map((item) => item.startsWith("test_") ? item.slice(5) : item)
    )
  );
  const hasConfiguredTests = normalizedEnabledTests.length > 0;

  if (!hasConfiguredTests) {
    delete existingPackConfig.enabledTests;
  } else {
    existingPackConfig.enabledTests = normalizedEnabledTests;
  }

  nextConfigs[normalizedPack] = normalizePackConfigShape(existingPackConfig, normalizedPack);
  return nextConfigs;
}

function getSelectedTerritoryValue() {
  return String(document.getElementById("territory")?.value || "").trim();
}

function applyTerritoryToPackConfig(packName, territory) {
  const normalizedPack = String(packName || "").trim().toLowerCase();
  if (!normalizedPack) {
    return;
  }

  const existingConfig = {
    ...(packConfigsByPack[normalizedPack] || getDefaultPackConfig(normalizedPack)),
  };

  if (territory) {
    existingConfig.territory = territory;
  } else {
    delete existingConfig.territory;
  }

  packConfigsByPack[normalizedPack] = existingConfig;
}

function updateTerritoryVisibilityForPack(packName) {
  const normalizedPack = String(packName || "").trim().toLowerCase();
  const territoryGroup = document.getElementById("territoryGroup");
  const territorySelect = document.getElementById("territory");
  const hideTerritory = SUSTAINABILITY_PACKS.has(normalizedPack);

  if (territoryGroup) {
    territoryGroup.style.display = hideTerritory ? "none" : "";
  }

  if (hideTerritory) {
    if (territorySelect) {
      territorySelect.value = "";
      territorySelect.innerHTML = "";
    }
    applyTerritoryToPackConfig(normalizedPack, "");
  }
}

async function fetchTerritoriesForPack(packName) {
  const normalizedPack = String(packName || "").trim().toLowerCase();
  if (!normalizedPack) {
    return [];
  }

  if (Array.isArray(territoriesByPack[normalizedPack])) {
    return territoriesByPack[normalizedPack];
  }

  try {
    const query = new URLSearchParams({ test_pack: normalizedPack });
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/field-config/territories?${query.toString()}`, {
      method: "GET",
      cache: "no-store",
    });

    if (!response.ok) {
      territoriesByPack[normalizedPack] = [];
      return [];
    }

    const payload = await response.json().catch(() => ({}));
    const territories = Array.isArray(payload?.territories)
      ? payload.territories.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    territoriesByPack[normalizedPack] = territories;
    return territories;
  } catch {
    territoriesByPack[normalizedPack] = [];
    return [];
  }
}

async function syncTerritorySelectorForSelectedPack() {
  const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
  const territorySelect = document.getElementById("territory");
  if (!selectedPack || !territorySelect) {
    return;
  }

  updateTerritoryVisibilityForPack(selectedPack);
  if (SUSTAINABILITY_PACKS.has(selectedPack)) {
    if (currentPackSelection === selectedPack) {
      renderSelectedPackConfig(selectedPack);
    }
    return;
  }

  const availableTerritories = await fetchTerritoriesForPack(selectedPack);
  territorySelect.innerHTML = "";

  if (availableTerritories.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Default";
    territorySelect.appendChild(option);
    territorySelect.value = "";
    applyTerritoryToPackConfig(selectedPack, "");
    if (currentPackSelection === selectedPack) {
      renderSelectedPackConfig(selectedPack);
    }
    return;
  }

  for (const territory of availableTerritories) {
    const option = document.createElement("option");
    option.value = territory;
    option.textContent = territory;
    territorySelect.appendChild(option);
  }

  const configuredTerritory = String(
    packConfigsByPack[selectedPack]?.territory
      || packConfigsByPack[selectedPack]?.Territory
      || ""
  ).trim();
  const chosenTerritory = availableTerritories.includes(configuredTerritory)
    ? configuredTerritory
    : availableTerritories[0];

  territorySelect.value = chosenTerritory;
  applyTerritoryToPackConfig(selectedPack, chosenTerritory);

  if (currentPackSelection === selectedPack) {
    renderSelectedPackConfig(selectedPack);
  }
}

function parsePackConfigInput(packConfigText, selectedPack) {
  const normalizedPack = String(selectedPack || "").trim().toLowerCase();
  const parsed = JSON.parse(packConfigText || "{}");

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Pack config must be a JSON object.");
  }

  const directConfig = parsed;
  const nestedConfig = parsed[normalizedPack];

  if (nestedConfig && typeof nestedConfig === "object" && !Array.isArray(nestedConfig)) {
    return normalizePackConfigShape(nestedConfig, normalizedPack);
  }

  return normalizePackConfigShape(directConfig, normalizedPack);
}

function renderSelectedPackConfig(selectedPack) {
  const normalizedPack = String(selectedPack || "").trim().toLowerCase();
  const packConfigEditor = document.getElementById("packConfigs");
  const config = withDefaultEnabledTests(
    { [normalizedPack]: packConfigsByPack[normalizedPack] || getDefaultPackConfig(normalizedPack) },
    normalizedPack
  )[normalizedPack];
  config.testPack = normalizedPack;
  packConfigsByPack[normalizedPack] = config;
  packConfigEditor.value = JSON.stringify(config, null, 2);
}

function syncPackConfigEditorWithSelectedPack() {
  const selectedPack = document.getElementById("testPacks").value;
  const packConfigEditor = document.getElementById("packConfigs");
  const normalizedPack = String(selectedPack || "").trim().toLowerCase();
  const selectedTerritory = getSelectedTerritoryValue();

  if (currentPackSelection) {
    try {
      const currentConfig = parsePackConfigInput(packConfigEditor.value, currentPackSelection);
      if (selectedTerritory) {
        currentConfig.territory = selectedTerritory;
      }
      packConfigsByPack[currentPackSelection] = withDefaultEnabledTests(
        { [currentPackSelection]: currentConfig },
        currentPackSelection
      )[currentPackSelection];
    } catch {
      // Keep current editor value if invalid, but do not switch contexts.
      document.getElementById("testPacks").value = currentPackSelection;
      setStatus("Pack configs JSON is invalid.", true);
      return;
    }
  }

  currentPackSelection = normalizedPack;
  renderSelectedPackConfig(normalizedPack);
}

function getExcelUserEmail() {
  const officeMailboxEmail = Office?.context?.mailbox?.userProfile?.emailAddress;
  const officeProfileEmail = Office?.context?.userProfile?.emailAddress;

  const email = officeMailboxEmail || officeProfileEmail || DEFAULT_EXCEL_EMAIL;
  return String(email).trim().toLowerCase();
}

function formatBackendErrorDetail(detail) {
  if (!detail) {
    return null;
  }

  if (typeof detail === "string") {
    return detail;
  }

  if (typeof detail === "object") {
    const message = detail.message || "Backend error";
    const pythonError = detail.python_error || detail.pythonError || null;
    const traceback = Array.isArray(detail.traceback) ? detail.traceback.join("\n") : null;

    const parts = [message];
    if (pythonError) {
      parts.push(`Python: ${pythonError}`);
    }
    if (traceback) {
      parts.push(`Traceback:\n${traceback}`);
    }
    return parts.join("\n\n");
  }

  return String(detail);
}

async function getDevelopmentFetchDiagnostics(backendUrl) {
  try {
    const healthResponse = await fetch(`${backendUrl}/health`, {
      method: "GET",
      cache: "no-store",
    });

    const body = await healthResponse.text().catch(() => "");
    if (!healthResponse.ok) {
      return `Could not reach Python validation endpoint cleanly. Health returned HTTP ${healthResponse.status}. Response: ${body || "<empty>"}`;
    }

    return `Python backend is reachable at ${backendUrl}, but /validate-range failed before a response could be read. Check backend logs for request handling errors.`;
  } catch (diagError) {
    return `Could not reach Python backend at ${backendUrl}. Ensure backend is running with TLS and reachable from Office. Root fetch error: ${diagError?.message || "Unknown network error"}`;
  }
}

async function getActiveSheetName() {
  try {
    return await Excel.run(async (context) => {
      const worksheet = context.workbook.worksheets.getActiveWorksheet();
      worksheet.load(["name"]);
      await context.sync();
      return worksheet.name || null;
    });
  } catch {
    return null;
  }
}

async function hydrateSelectedPackConfigFromServer() {
  const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
  if (!selectedPack) {
    return;
  }

  const excelUserEmail = getExcelUserEmail();
  const sheetName = await getActiveSheetName();
  if (!excelUserEmail || !sheetName) {
    return;
  }

  const query = new URLSearchParams({
    test_pack: selectedPack,
    sheet_name: sheetName,
  });

  try {
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/pack-config?${query.toString()}`, {
      method: "GET",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return;
    }

    const payload = await response.json().catch(() => ({}));
    const persistedConfig = payload && typeof payload.pack_config === "object" && !Array.isArray(payload.pack_config)
      ? payload.pack_config
      : null;

    if (!persistedConfig) {
      return;
    }

    const mergedConfig = withDefaultEnabledTests(
      {
        [selectedPack]: {
          ...getDefaultPackConfig(selectedPack),
          ...(packConfigsByPack[selectedPack] || {}),
          ...persistedConfig,
        },
      },
      selectedPack
    )[selectedPack];

    packConfigsByPack[selectedPack] = mergedConfig;
    if (currentPackSelection === selectedPack) {
      renderSelectedPackConfig(selectedPack);
    }
  } catch {
    // Best-effort hydration only.
  }
}


Office.onReady(async () => {
  const testPackSelect = document.getElementById("testPacks");
  const excelUserEmail = getExcelUserEmail();
  const availablePacks = populatePackSelect(await loadSubscribedPackValues(excelUserEmail));

  const defaultPackFromConfig = String(CONFIG.DEFAULT_PACK || "").trim().toLowerCase();
  const fallbackPack = availablePacks[0] || "risk_and_premium";
  const initialPack = availablePacks.includes(defaultPackFromConfig)
    ? defaultPackFromConfig
    : fallbackPack;

  testPackSelect.value = initialPack;
  if (!testPackSelect.value) {
    testPackSelect.value = fallbackPack;
  }

  packConfigsByPack = Object.fromEntries(
    availablePacks.map((packName) => [packName, getDefaultPackConfig(packName)])
  );

  currentPackSelection = String(testPackSelect.value || "").trim().toLowerCase();
  renderSelectedPackConfig(currentPackSelection);
  await syncTerritorySelectorForSelectedPack();
  document.getElementById("testPacks").addEventListener("change", async () => {
    syncPackConfigEditorWithSelectedPack();
    await hydrateSelectedPackConfigFromServer();
    await syncTerritorySelectorForSelectedPack();
  });
  await hydrateSelectedPackConfigFromServer();
  await syncTerritorySelectorForSelectedPack();
  document.getElementById("territory")?.addEventListener("change", () => {
    const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
    const territory = getSelectedTerritoryValue();
    applyTerritoryToPackConfig(selectedPack, territory);
    if (currentPackSelection === selectedPack) {
      renderSelectedPackConfig(selectedPack);
    }
  });
  document.getElementById("runValidation").addEventListener("click", runValidation);
  document.getElementById("clearTable")?.addEventListener("click", clearTableFormattingAndComments);
  document.getElementById("extractResults")?.addEventListener("click", extractValidationResults);
  document.getElementById("visualiseResults")?.addEventListener("click", visualiseValidationResults);
  document.getElementById("rulesEngine")?.addEventListener("click", openRulesEngine);
  // Initialize button states (Extract / Visualise disabled until validation run)
  updateActionButtons();
});

function setStatus(message, isError = false) {
  const status = document.getElementById("status");
  status.textContent = message;
  status.style.color = isError ? "#b00020" : "#1e4620";
}

function columnToA1(colIndexZeroBased) {
  let dividend = colIndexZeroBased + 1;
  let columnName = "";

  while (dividend > 0) {
    const modulo = (dividend - 1) % 26;
    columnName = String.fromCharCode(65 + modulo) + columnName;
    dividend = Math.floor((dividend - modulo) / 26);
  }

  return columnName;
}

function buildAddressRow(globalRowZeroBased, startColZeroBased, columnCount) {
  const rowNumber = globalRowZeroBased + 1;
  const rowAddresses = [];

  for (let colOffset = 0; colOffset < columnCount; colOffset += 1) {
    const colName = columnToA1(startColZeroBased + colOffset);
    rowAddresses.push(`${colName}${rowNumber}`);
  }

  return rowAddresses;
}

function getWorkbookName() {
  try {
    const url = String(Office?.context?.document?.url || "").trim();
    if (!url) {
      return null;
    }
    const withoutQuery = url.split("?")[0];
    const lastSegment = withoutQuery.split("/").pop() || "";
    return lastSegment ? decodeURIComponent(lastSegment) : null;
  } catch {
    return null;
  }
}

function resolveReferenceColumnIndex(headerRow, selectedPack) {
  const currentPackConfig = packConfigsByPack[String(selectedPack || "").trim().toLowerCase()] || {};
  const configuredRef = String(
    currentPackConfig.ID
      || currentPackConfig.id
      || currentPackConfig.UMR
      || currentPackConfig.UTIColumn
      || "Unique Market Reference (UMR)"
  ).trim();

  const candidates = Array.from(new Set([
    configuredRef,
    "Unique Market Reference (UMR)",
    "Agreement No",
    "Record ID",
    "Submission ID",
    "Company Identifier",
    "Entity Name",
  ].filter(Boolean)));

  return headerRow.findIndex((header) => {
    const headerText = String(header || "").trim();
    return candidates.includes(headerText);
  });
}

function isCellEmpty(value) {
  return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
}

function findNonEmptyBounds(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return null;
  }

  let minRow = Number.POSITIVE_INFINITY;
  let maxRow = Number.NEGATIVE_INFINITY;
  let minCol = Number.POSITIVE_INFINITY;
  let maxCol = Number.NEGATIVE_INFINITY;

  for (let r = 0; r < values.length; r += 1) {
    const row = values[r] || [];
    for (let c = 0; c < row.length; c += 1) {
      if (!isCellEmpty(row[c])) {
        minRow = Math.min(minRow, r);
        maxRow = Math.max(maxRow, r);
        minCol = Math.min(minCol, c);
        maxCol = Math.max(maxCol, c);
      }
    }
  }

  if (!Number.isFinite(minRow)) {
    return null;
  }

  return { minRow, maxRow, minCol, maxCol };
}

async function resolveValidationRangeMeta() {
  return Excel.run(async (context) => {
    const workbook = context.workbook;
    const worksheet = workbook.worksheets.getActiveWorksheet();
    const selectedRange = workbook.getSelectedRange();

    worksheet.load(["name"]);
    selectedRange.load(["rowIndex", "columnIndex", "rowCount", "columnCount", "values"]);
    await context.sync();

    const selectionHasHeaderAndData = selectedRange.rowCount >= 2 && selectedRange.columnCount >= 1;
    if (selectionHasHeaderAndData) {
      const headerValues = selectedRange.values?.[0] || [];
      const hasHeaderContent = headerValues.some((value) => !isCellEmpty(value));
      if (hasHeaderContent) {
        return {
          startRow: selectedRange.rowIndex,
          startCol: selectedRange.columnIndex,
          rowCount: selectedRange.rowCount,
          columnCount: selectedRange.columnCount,
          headerValues,
          headerAddresses: buildAddressRow(
            selectedRange.rowIndex,
            selectedRange.columnIndex,
            selectedRange.columnCount
          ),
          sheetName: worksheet.name,
          source: "selection",
        };
      }
    }

    const usedRange = worksheet.getUsedRangeOrNullObject();
    usedRange.load(["isNullObject", "rowIndex", "columnIndex", "rowCount", "columnCount", "values"]);
    await context.sync();

    if (usedRange.isNullObject) {
      throw new Error("No data found on the active sheet.");
    }

    const bounds = findNonEmptyBounds(usedRange.values || []);
    if (!bounds) {
      throw new Error("No data found on the active sheet.");
    }

    const trimmedStartRow = usedRange.rowIndex + bounds.minRow;
    const trimmedStartCol = usedRange.columnIndex + bounds.minCol;
    const trimmedRowCount = bounds.maxRow - bounds.minRow + 1;
    const trimmedColumnCount = bounds.maxCol - bounds.minCol + 1;

    if (trimmedRowCount < 2) {
      throw new Error("Could not identify a table with a header row and at least one data row.");
    }

    const headerValues = (usedRange.values[bounds.minRow] || []).slice(bounds.minCol, bounds.maxCol + 1);

    return {
      startRow: trimmedStartRow,
      startCol: trimmedStartCol,
      rowCount: trimmedRowCount,
      columnCount: trimmedColumnCount,
      headerValues,
      headerAddresses: buildAddressRow(trimmedStartRow, trimmedStartCol, trimmedColumnCount),
      sheetName: worksheet.name,
      source: "sheet",
    };
  });
}

async function clearTableFormattingAndComments() {
  const clearButton = document.getElementById("clearTable");
  const runButton = document.getElementById("runValidation");

  if (clearButton) {
    clearButton.disabled = true;
  }
  if (runButton) {
    runButton.disabled = true;
  }

  try {
    setStatus("Detecting table on active sheet...");
    const tableMeta = await resolveValidationRangeMeta();

    setStatus("Clearing comments...");
    await clearCommentsInRange(
      tableMeta.startRow,
      tableMeta.startCol,
      tableMeta.rowCount,
      tableMeta.columnCount
    );

    setStatus("Clearing cell highlights...");
    await Excel.run(async (context) => {
      const worksheet = context.workbook.worksheets.getActiveWorksheet();
      const range = worksheet.getRangeByIndexes(
        tableMeta.startRow,
        tableMeta.startCol,
        tableMeta.rowCount,
        tableMeta.columnCount
      );
      range.format.fill.clear();
      await context.sync();
    });

    setStatus("Cleared all comments and highlights in the table.");
  } catch (error) {
    setStatus(`Clear failed: ${error?.message || "Unexpected error"}`, true);
  } finally {
    if (clearButton) {
      clearButton.disabled = false;
    }
    if (runButton) {
      runButton.disabled = false;
    }
  }
}

async function readRangeValues(startRow, startCol, rowCount, columnCount) {
  return Excel.run(async (context) => {
    const worksheet = context.workbook.worksheets.getActiveWorksheet();
    const range = worksheet.getRangeByIndexes(startRow, startCol, rowCount, columnCount);
    range.load("values");
    await context.sync();
    return range.values;
  });
}

async function clearCommentsInRange(startRow, startCol, rowCount, columnCount) {
  // Clear all comments in the specified range by loading all worksheet comments
  // and deleting those whose cell falls within the range
  await Excel.run(async (context) => {
    const worksheet = context.workbook.worksheets.getActiveWorksheet();
    const comments = worksheet.comments;
    comments.load("items");
    await context.sync();

    if (comments.items.length === 0) {
      return;
    }

    // Build a set of addresses in our range for quick lookup
    const addressSet = new Set();
    for (let r = 0; r < rowCount; r++) {
      for (let c = 0; c < columnCount; c++) {
        const colLetter = columnToA1(startCol + c);
        const rowNum = startRow + r + 1; // Excel rows are 1-based
        addressSet.add(`${colLetter}${rowNum}`);
      }
    }

    // Load the location of each comment — store the location proxy
    const commentLocations = [];
    for (const comment of comments.items) {
      const location = comment.getLocation();
      location.load("address");
      commentLocations.push({ comment, location });
    }
    await context.sync();

    // Delete comments that are in our range
    for (const { comment, location } of commentLocations) {
      const cellAddress = location.address;
      // Address may be "Sheet1!A1" — extract just the cell part
      const cellPart = cellAddress.includes("!") ? cellAddress.split("!")[1] : cellAddress;
      if (addressSet.has(cellPart)) {
        comment.delete();
      }
    }

    await context.sync();
  });
}

async function applyResultsToSheet(results, maxSeverityScore) {
  await Excel.run(async (context) => {
    const worksheet = context.workbook.worksheets.getActiveWorksheet();

    // Phase 1: Apply all fill colors (no sync needed between each)
    const cellsWithFailures = [];
    const cellsWithoutFailures = [];

    for (const result of results) {
      const cell = worksheet.getRange(result.address);
      // Use severityScore for heatmap coloring (falls back to failCount for compatibility)
      const severityScore = result.severityScore !== undefined ? result.severityScore : result.failCount;
      const color = heatmapColor(severityScore, maxSeverityScore);
      cell.format.fill.color = color;

      if (result.failCount > 0) {
        // Header issues should be highlighted but comments stay in frontend status.
        if (result.rowIndex > 0) {
          cellsWithFailures.push({ address: result.address, comment: result.comment });
        } else {
          cellsWithoutFailures.push(result.address);
        }
      } else {
        cellsWithoutFailures.push(result.address);
      }
    }

    await context.sync();

    // Phase 2: Load all existing comments once
    const comments = worksheet.comments;
    comments.load("items");
    await context.sync();

    // Build a map of existing comment addresses
    const commentLocations = [];
    for (const comment of comments.items) {
      const location = comment.getLocation();
      location.load("address");
      commentLocations.push({ comment, location });
    }
    await context.sync();

    const existingCommentMap = new Map();
    for (const { comment, location } of commentLocations) {
      const addr = location.address;
      const cellPart = addr.includes("!") ? addr.split("!")[1] : addr;
      existingCommentMap.set(cellPart, comment);
    }

    // Phase 3: Add/update comments for failed cells
    for (const { address, comment } of cellsWithFailures) {
      const existing = existingCommentMap.get(address);
      if (existing) {
        existing.content = comment;
      } else {
        worksheet.comments.add(address, comment, Excel.ContentType.plain);
      }
    }

    // Phase 4: Delete comments for passing cells (already cleared at start, but just in case)
    for (const address of cellsWithoutFailures) {
      const existing = existingCommentMap.get(address);
      if (existing) {
        existing.delete();
      }
    }

    await context.sync();
  });
}

async function buildFailureExportRows() {
  return Excel.run(async (context) => {
    const workbook = context.workbook;
    const worksheet = lastValidationSourceSheetName
      ? workbook.worksheets.getItemOrNullObject(lastValidationSourceSheetName)
      : workbook.worksheets.getActiveWorksheet();

    worksheet.load("isNullObject");
    await context.sync();

    if (worksheet.isNullObject) {
      throw new Error("Could not find the source sheet from the last validation run.");
    }

    const usedRange = worksheet.getUsedRangeOrNullObject();
    usedRange.load(["isNullObject", "values"]);
    await context.sync();

    if (usedRange.isNullObject) {
      throw new Error("Could not find data on the active sheet.");
    }

    const allValues = usedRange.values || [];
    const headerRow = allValues[0] || [];
    const umrColumnIndex = resolveReferenceColumnIndex(headerRow, currentPackSelection);

    const fieldNameMap = {};
    for (let index = 0; index < headerRow.length; index += 1) {
      fieldNameMap[index] = String(headerRow[index] || "").trim();
    }

    const dataRows = [];
    for (const result of lastValidationResults) {
      if (!(result.failCount > 0 && result.rowIndex > 0)) {
        continue;
      }

      const rowOffset = result.rowIndex;
      let umrValue = "";
      if (umrColumnIndex >= 0 && allValues[rowOffset] && allValues[rowOffset][umrColumnIndex]) {
        umrValue = String(allValues[rowOffset][umrColumnIndex]).trim();
      }

      const fieldName = fieldNameMap[result.columnIndex] || "";
      const value = result.value === null || result.value === undefined ? "" : String(result.value);
      const failedTests = Array.isArray(result.failedTests) ? result.failedTests : [];

      if (failedTests.length > 0) {
        for (const testMessage of failedTests) {
          let severity = "";
          let testId = "Unknown";
          let description = "";
          let testType = "";
          if (typeof testMessage === "string") {
            const rawMessage = String(testMessage || "").trim();
            const match = rawMessage.match(/^\[(.*?)\]\s+([A-Za-z0-9_]+):\s*(.*)$/);
            severity = match ? match[1] : "";
            testId = match ? match[2] : "Unknown";
            description = match ? match[3] : rawMessage;
          } else if (typeof testMessage === "object" && testMessage !== null) {
            severity = String(testMessage.severity || "");
            testId = String(testMessage.testId || "Unknown");
            description = String(testMessage.description || "");
            testType = String(testMessage.testType || "");
          }
          dataRows.push({ umr: umrValue, testId, fieldName, value, severity, description, testType });
        }
      } else {
        dataRows.push({ umr: umrValue, testId: "Unknown", fieldName, value, severity: "", description: "", testType: "" });
      }
    }

    return dataRows;
  });
}

async function extractValidationResults() {
  const extractButton = document.getElementById("extractResults");
  
  if (!lastValidationResults || lastValidationResults.length === 0) {
    setStatus("No validation results to extract. Please run validation first.", true);
    return;
  }

  if (extractButton) {
    extractButton.disabled = true;
  }

  try {
    setStatus("Preparing CSV export...");
    const exportRows = await buildFailureExportRows();

    const headers = ["UMR", "Test ID", "Field Name", "Value", "Severity", "Test Type", "Description"];
    const rowsForCsv = [headers, ...exportRows.map((row) => [
      row.umr,
      row.testId,
      row.fieldName,
      row.value,
      row.severity,
      row.testType || "",
      row.description,
    ])];
    const csvEscape = (input) => `"${String(input ?? "").replace(/"/g, '""')}"`;
    const csvContent = rowsForCsv.map((row) => row.map(csvEscape).join(",")).join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const link = document.createElement("a");
    link.href = url;
    link.download = `axios_${timestamp}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    
    setStatus(`Export complete: ${exportRows.length} failure rows downloaded as CSV.`);
  } catch (error) {
    setStatus(`Extract failed: ${error?.message || "Unexpected error"}`, true);
  } finally {
    if (extractButton) {
      extractButton.disabled = false;
    }
  }
}

async function visualiseValidationResults() {
  const visualiseButton = document.getElementById("visualiseResults");

  if (!lastValidationResults || lastValidationResults.length === 0) {
    setStatus("No validation results to visualise. Please run validation first.", true);
    return;
  }

  if (visualiseButton) {
    visualiseButton.disabled = true;
  }

  try {
    setStatus("Preparing front-end visualisation...");
    const exportRows = await buildFailureExportRows();

    // Compute simple KPIs from exportRows (no Excel sheet interaction)
    const failedUmrs = new Set(exportRows.map((r) => String(r.umr || "").trim()).filter(Boolean));
    const failedFields = new Set(exportRows.map((r) => String(r.fieldName || "").trim()).filter(Boolean));
    const failedTests = new Set(exportRows.map((r) => String(r.testId || "").trim()).filter(Boolean));

    let totalSubmittedUmrs = null; // attempt to read totals from source sheet
    let totalFields = null;
    try {
      await Excel.run(async (context) => {
        const workbook = context.workbook;
        const worksheet = lastValidationSourceSheetName
          ? workbook.worksheets.getItemOrNullObject(lastValidationSourceSheetName)
          : workbook.worksheets.getActiveWorksheet();
        worksheet.load('isNullObject');
        await context.sync();
        if (worksheet.isNullObject) return;
        const usedRange = worksheet.getUsedRangeOrNullObject();
        usedRange.load(['isNullObject', 'values']);
        await context.sync();
        if (usedRange.isNullObject) return;
        const allValues = usedRange.values || [];
        if (!allValues || allValues.length === 0) return;
        const header = allValues[0] || [];
        totalFields = header.length || null;
        const umrCol = resolveReferenceColumnIndex(header, currentPackSelection);
        if (umrCol >= 0) {
          const umrSet = new Set();
          for (let i = 1; i < allValues.length; i++) {
            const v = allValues[i] && allValues[i][umrCol];
            if (v !== null && v !== undefined && String(v).trim() !== '') umrSet.add(String(v).trim());
          }
          totalSubmittedUmrs = umrSet.size;
        }
      });
    } catch (e) {
      // best-effort only; leave totals as null if reading fails
    }
    const totalTests = Array.isArray(lastValidationExecutedTests) ? lastValidationExecutedTests.length : null;

    const formatPercent = (numerator, denominator) => {
      if (!denominator) return "N/A";
      return `${((numerator / denominator) * 100).toFixed(1)}%`;
    };

    const kpis = [
      { title: "Submissions Failed", value: String(failedUmrs.size) },
      { title: "Submissions Failed %", value: formatPercent(failedUmrs.size, totalSubmittedUmrs) },
      { title: "Fields Failed", value: String(failedFields.size) },
      { title: "Fields Failed %", value: formatPercent(failedFields.size, totalFields) },
      { title: "Tests Failed", value: String(failedTests.size) },
      { title: "Tests Failed %", value: formatPercent(failedTests.size, totalTests) },
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
        return totalSubmittedUmrs ? `of ${totalSubmittedUmrs} total submissions` : '&nbsp;';
      }
      if (title.includes("field")) {
        return totalFields ? `of ${totalFields} total fields` : '&nbsp;';
      }
      if (title.includes("test")) {
        return totalTests ? `of ${totalTests} tests run` : '&nbsp;';
      }
      return '&nbsp;';
    };

    // Prepare severity-composed datasets for bar charts
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

    const fieldCounts = buildSeverityDataset(r => r.fieldName);
    const testCounts = buildSeverityDataset(r => r.testId);
    const umrCounts = buildSeverityDataset(r => r.umr);

    const safeJson = (value) => JSON.stringify(value)
      .replace(/</g, '\\u003c')
      .replace(/>/g, '\\u003e')
      .replace(/&/g, '\\u0026')
      .replace(/\u2028/g, '\\u2028')
      .replace(/\u2029/g, '\\u2029');
    const datasetsJson = safeJson({ test: testCounts, trade: fieldCounts, umr: umrCounts });
    const allRowsJson = safeJson(exportRows.map(r => ({
      umr: r.umr || '',
      testId: r.testId || '',
      fieldName: r.fieldName || '',
      severity: r.severity || '',
      description: r.description || ''
    })));

    // Generate Sankey PNG base64 for embedding (stable rendering path)
    let sankeyBase64 = null;
    try {
      sankeyBase64 = await buildSankeyPngBase64(exportRows);
    } catch (e) {
      // continue without sankey
    }

    // Build HTML for new tab
    const win = window.open('', '_blank');
    if (!win) {
      setStatus('Could not open new tab — popup blocked.', true);
      return;
    }

    const escapeHtml = (s) => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

    const nowStr = new Date().toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
    const packLabel = formatPackLabel(lastValidationPack || currentPackSelection || "Unknown");

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

    /* ── Nav ── */
    .nav { display:flex; align-items:center; gap:16px; padding:0 24px; height:52px; background:var(--nav-bg); border-bottom:1px solid #1e2028; position:sticky; top:0; z-index:100; }
    .nav-logo { display:flex; align-items:center; gap:8px; color:#fff; font-size:14px; font-weight:600; letter-spacing:-.2px; text-decoration:none; }
    .nav-logo svg { flex-shrink:0; }
    .nav-divider { width:1px; height:20px; background:#2e3140; }
    .nav-title { color:var(--nav-text); font-size:13px; }
    .nav-spacer { flex:1; }
    .nav-meta { color:var(--text-3); font-size:12px; }
    .nav-badge { padding:3px 8px; border-radius:4px; font-size:11px; font-weight:600; background:#1e2028; color:var(--nav-text); border:1px solid #2e3140; }

    /* ── Page shell ── */
    .page { max-width:1280px; margin:0 auto; padding:24px 24px 48px; }

    /* ── Page header ── */
    .page-header { display:flex; align-items:flex-start; justify-content:space-between; margin-bottom:24px; }
    .page-header h1 { margin:0; font-size:20px; font-weight:700; letter-spacing:-.3px; }
    .page-header p { margin:4px 0 0; color:var(--text-2); font-size:13px; }
    .header-actions { display:flex; gap:8px; align-items:center; }
    .btn { display:inline-flex; align-items:center; gap:6px; padding:7px 14px; border-radius:var(--radius); font-size:13px; font-weight:500; cursor:pointer; border:1px solid var(--border); background:var(--surface); color:var(--text-1); transition:background .12s, box-shadow .12s; }
    .btn:hover { background:#f0f2f5; }
    .btn-primary { background:var(--accent); color:#fff; border-color:transparent; }
    .btn-primary:hover { background:#3d5ce6; }

    /* ── Stat row ── */
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

    /* ── Panels ── */
    .panel { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); box-shadow:var(--shadow); margin-bottom:16px; }
    .panel-header { display:flex; align-items:center; justify-content:space-between; padding:14px 18px 12px; border-bottom:1px solid var(--border); }
    .panel-title { font-size:13px; font-weight:600; color:var(--text-1); margin:0; }
    .panel-subtitle { font-size:12px; color:var(--text-3); margin-top:2px; }
    .panel-body { padding:18px; }

    /* ── Toggle tabs ── */
    .tab-group { display:inline-flex; gap:2px; background:#f0f2f5; border-radius:6px; padding:3px; border:1px solid var(--border); }
    .tab-btn { padding:5px 14px; border:none; background:transparent; border-radius:5px; font-size:12px; font-weight:500; color:var(--text-2); cursor:pointer; transition:background .12s, color .12s; white-space:nowrap; }
    .tab-btn.active { background:var(--surface); color:var(--text-1); box-shadow:0 1px 3px rgba(0,0,0,.1); font-weight:600; }
    .tab-btn:hover:not(.active) { color:var(--text-1); background:rgba(255,255,255,.6); }

    /* ── Horizontal bar chart ── */
    .chart-wrap { padding:4px 0; }
    .bar-row { display:grid; grid-template-columns:200px 1fr 52px; align-items:center; gap:10px; padding:5px 0; border-bottom:1px solid #f3f4f6; }
    .bar-row:last-child { border-bottom:none; }
    .bar-label { font-size:12px; color:var(--text-1); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .bar-track { background:#f0f2f5; border-radius:4px; height:12px; overflow:hidden; display:flex; }
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

    /* ── Sankey ── */
    .sankey-wrap { background:#fff; border-radius:8px; overflow:hidden; border:none; box-shadow:none; }
    .sankey-wrap img { display:block; width:100%; height:auto; min-height:180px; object-fit:contain; image-rendering:auto; }

    /* ── Failure table ── */
    .data-table { width:100%; border-collapse:collapse; font-size:12px; }
    .data-table th { padding:9px 12px; text-align:left; font-size:11px; font-weight:600; color:var(--text-2); text-transform:uppercase; letter-spacing:.4px; background:#f8f9fb; border-bottom:2px solid var(--border); white-space:nowrap; }
    .data-table td { padding:9px 12px; border-bottom:1px solid var(--border); color:var(--text-1); vertical-align:top; }
    .data-table tr:last-child td { border-bottom:none; }
    .data-table tr:hover td { background:#f8f9fb; }
    .badge { display:inline-flex; align-items:center; padding:2px 8px; border-radius:99px; font-size:11px; font-weight:600; }
    .badge-critical { background:#fee2e2; color:#b91c1c; }
    .badge-error { background:#ffedd5; color:#c2410c; }
    .badge-warning { background:#fef9c3; color:#854d0e; }
    .badge-info { background:#e0f2fe; color:#075985; }
    .badge-default { background:#f0f2f5; color:var(--text-2); }
    .mono { font-family: 'Menlo','Consolas',monospace; font-size:11px; }

    /* ── Section label ── */
    .section-label { font-size:11px; font-weight:700; color:var(--text-3); text-transform:uppercase; letter-spacing:.8px; margin:0 0 12px; }

    /* ── Empty state ── */
    .empty { padding:40px 0; text-align:center; color:var(--text-3); font-size:13px; }

    /* ── Pagination ── */
    .pagination { display:flex; align-items:center; gap:4px; padding:12px 18px; border-top:1px solid var(--border); }
    .pagination .page-info { font-size:12px; color:var(--text-2); margin-right:auto; }
    .pg-btn { display:inline-flex; align-items:center; justify-content:center; min-width:30px; height:28px; padding:0 8px; border-radius:5px; border:1px solid var(--border); background:var(--surface); font-size:12px; font-weight:500; color:var(--text-1); cursor:pointer; transition:background .1s; }
    .pg-btn:hover:not(:disabled) { background:#f0f2f5; }
    .pg-btn.active { background:var(--accent); color:#fff; border-color:var(--accent); }
    .pg-btn:disabled { opacity:.4; cursor:default; }
  </style>
</head>
<body>

<nav class="nav">
  <a class="nav-logo" href="#">
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect width="20" height="20" rx="5" fill="#4f6ef7"/><path d="M5 14L8 8l3 4 2-3 2 5" stroke="#fff" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
    Axios
  </a>
  <div class="nav-divider"></div>
  <span class="nav-title">Reporting Validation</span>
  <div class="nav-spacer"></div>
  <span class="nav-meta">Pack: <strong style="color:#fff">${escapeHtml(packLabel)}</strong></span>
  <div class="nav-divider"></div>
  <span class="nav-meta">${escapeHtml(nowStr)}</span>
  <span class="nav-badge">${exportRows.length} failure rows</span>
</nav>

<div class="page">

  <div class="page-header">
    <div>
      <h1>Validation Results</h1>
      <p>Overview of validation testing for the selected pack — review failures by test, field and submission.</p>
    </div>
  </div>

  <!-- KPI strip -->
  <div class="stat-grid">
    ${kpis.map((k,i)=>{
      const accent = getKpiAccent(k);
      const sub = getKpiSub(k);
      return `<div class="stat-card ${accent}"><div class="stat-label">${escapeHtml(k.title)}</div><div class="stat-value">${escapeHtml(k.value)}</div><div class="stat-sub">${sub}</div></div>`;
    }).join('')}
  </div>

  <!-- Flow diagram -->
  ${sankeyBase64 ? `
  <div class="panel" style="margin-bottom:16px">
    <div class="panel-header">
      <div><div class="panel-title">Test Flow Overview</div><div class="panel-subtitle">Test flow representing the outcomes of the validation run</div></div>
    </div>
    <div class="panel-body" style="padding:12px 18px 18px;background:#fff">
      <div class="sankey-wrap">
        <img alt="High quality Sankey diagram" src="data:image/png;base64,${sankeyBase64}" />
      </div>
    </div>
  </div>` : ''}

  <!-- Bar chart panel -->
  <div class="panel" style="margin-bottom:16px">
    <div class="panel-header">
      <div>
        <div class="panel-title">Top Failure Breakdown</div>
        <div class="panel-subtitle">Top 10 by failure count, split by severity</div>
      </div>
      <div class="tab-group" id="bar-controls"></div>
    </div>
    <div class="panel-body">
      <div class="chart-wrap" id="bar-container"></div>
    </div>
  </div>

  <!-- Failure detail table -->
  <div class="panel">
    <div class="panel-header">
      <div>
        <div class="panel-title">Failure Detail</div>
        <div class="panel-subtitle">Complete failure analysis</div>
      </div>
      <span style="font-size:12px;color:var(--text-3)">${exportRows.length} rows</span>
    </div>
    <div class="panel-body" style="padding:0;overflow-x:auto;">
      ${exportRows.length === 0 ? '<div class="empty">No failures recorded.</div>' : `
      <table class="data-table" id="failure-table">
        <thead><tr>
          <th>UMR</th>
          <th>Test ID</th>
          <th>Field</th>
          <th>Severity</th>
          <th>Description</th>
        </tr></thead>
        <tbody id="failure-tbody"></tbody>
      </table>
      <div class="pagination" id="pagination"></div>
      `}
    </div>
  </div>

</div><!-- /page -->

<script>
(function(){
  const datasets = ${datasetsJson};
  const labels = { test: 'Test', trade: 'Field', umr: 'Submission' };

  function renderBars(key) {
    const rows = datasets[key] || [];
    const container = document.getElementById('bar-container');
    container.innerHTML = '';
    if (!rows.length) {
      container.innerHTML = '<div class="empty">No data available for this view.</div>';
      return;
    }
    const max = Math.max(...rows.map(r => r.total), 1);

    const legend = document.createElement('div');
    legend.className = 'severity-legend';
    legend.innerHTML =
      '<span class="severity-legend-item"><span class="severity-dot warn"></span>Warning</span>' +
      '<span class="severity-legend-item"><span class="severity-dot error"></span>Error</span>' +
      '<span class="severity-legend-item"><span class="severity-dot critical"></span>Critical</span>';
    container.appendChild(legend);

    rows.forEach((r) => {
      const warningPct = max ? ((r.WARNING || 0) / max) * 100 : 0;
      const errorPct = max ? ((r.ERROR || 0) / max) * 100 : 0;
      const criticalPct = max ? ((r.CRITICAL || 0) / max) * 100 : 0;
      const row = document.createElement('div');
      row.className = 'bar-row';
      row.innerHTML =
        '<div class="bar-label" title="' + String(r.label || '').replace(/"/g,'&quot;') + '">' + String(r.label || '') + '</div>' +
        '<div class="bar-track">' +
          '<div class="bar-seg warn" style="width:' + warningPct + '%" title="Warning: ' + (r.WARNING || 0) + '"></div>' +
          '<div class="bar-seg error" style="width:' + errorPct + '%" title="Error: ' + (r.ERROR || 0) + '"></div>' +
          '<div class="bar-seg critical" style="width:' + criticalPct + '%" title="Critical: ' + (r.CRITICAL || 0) + '"></div>' +
        '</div>' +
        '<div class="bar-count">' + (r.total || 0) + '</div>';
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
        document.querySelectorAll('#bar-controls .tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderBars(k);
      });
      controls.appendChild(btn);
    });
    renderBars('test');
  }

  // ── Failure table pagination ──
  const PAGE_SIZE = 10;
  const allRows = ${allRowsJson};
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
    tbody.innerHTML = slice.map(r => {
      const sev = String(r.severity || '').toUpperCase();
      const bc = sev === 'CRITICAL' ? 'badge-critical' : sev === 'ERROR' ? 'badge-error' : sev === 'WARNING' ? 'badge-warning' : sev === 'INFO' ? 'badge-info' : 'badge-default';
      return '<tr>' +
        '<td class="mono">' + escHtml(r.umr || '\u2014') + '</td>' +
        '<td class="mono">' + escHtml(r.testId || '\u2014') + '</td>' +
        '<td>' + escHtml(r.fieldName || '\u2014') + '</td>' +
        '<td>' + (sev ? '<span class="badge ' + bc + '">' + escHtml(sev) + '</span>' : '\u2014') + '</td>' +
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
    let html = '<span class="page-info">Showing ' + start + '\u2013' + end + ' of ' + allRows.length + ' rows</span>';

    // Prev
    html += '<button class="pg-btn" id="pg-prev"' + (page <= 1 ? ' disabled' : '') + '>&lsaquo; Prev</button>';

    // Page numbers — show up to 7 with ellipsis
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
    pages.forEach(p => {
      if (p === '...') {
        html += '<span class="pg-btn" style="border:none;background:none;cursor:default">…</span>';
      } else {
        html += '<button class="pg-btn' + (p === page ? ' active' : '') + '" data-page="' + p + '">' + p + '</button>';
      }
    });

    // Next
    html += '<button class="pg-btn" id="pg-next"' + (page >= tp ? ' disabled' : '') + '>Next &rsaquo;</button>';

    pg.innerHTML = html;

    pg.querySelectorAll('[data-page]').forEach(btn => {
      btn.addEventListener('click', () => { currentPage = parseInt(btn.dataset.page, 10); renderTable(currentPage); renderPagination(currentPage); });
    });
    const prev = pg.querySelector('#pg-prev');
    const next = pg.querySelector('#pg-next');
    if (prev) prev.addEventListener('click', () => { if (currentPage > 1) { currentPage--; renderTable(currentPage); renderPagination(currentPage); } });
    if (next) next.addEventListener('click', () => { if (currentPage < totalPages()) { currentPage++; renderTable(currentPage); renderPagination(currentPage); } });
  }

  function setupTable() {
    if (!document.getElementById('failure-tbody')) return;
    renderTable(1);
    renderPagination(1);
  }

  let initialized = false;
  function init() {
    if (initialized) return;
    initialized = true;
    setupControls();
    setupTable();
  }

  // Robust init for document.write/new-tab flow.
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

    setStatus(`Visualisation opened in new tab: ${exportRows.length} failure rows.`);
  } catch (error) {
    setStatus(`Visualise failed: ${error?.message || "Unexpected error"}`, true);
  } finally {
    if (visualiseButton) {
      visualiseButton.disabled = false;
    }
  }
}

async function openRulesEngine() {
  const rulesButton = document.getElementById("rulesEngine");
  if (rulesButton) {
    rulesButton.disabled = true;
  }

  try {
    setStatus("Loading rules engine...");
    const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
    const rulesUrl = new URL(`${CONFIG.BACKEND_URL}/api/v1/rules-engine`);
    if (selectedPack) {
      rulesUrl.searchParams.set("test_pack", selectedPack);
    }

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
    const packLabel = formatPackLabel(selectedPack || "All Packs");

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
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect width="20" height="20" rx="5" fill="#4f6ef7"/><path d="M5 14L8 8l3 4 2-3 2 5" stroke="#fff" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
      Axios
    </a>
    <div class="nav-divider"></div>
    <span class="nav-title">Reporting Validation</span>
    <div class="nav-spacer"></div>
    <span class="nav-meta">Pack: <strong style="color:#fff">${packLabel}</strong></span>
    <div class="nav-divider"></div>
    <span class="nav-meta">${nowStr}</span>
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
              rule.test_type,
              rule.pack,
            ].map(norm).join(" ");
            return haystack.includes(q);
          })
          .sort((a, b) => {
            const byCol = clean(a.target_column).localeCompare(clean(b.target_column), undefined, { sensitivity: "base" });
            if (byCol !== 0) return byCol;
            const byRule = clean(a.rule_id).localeCompare(clean(b.rule_id), undefined, { sensitivity: "base" });
            if (byRule !== 0) return byRule;
            return clean(a.pack).localeCompare(clean(b.pack), undefined, { sensitivity: "base" });
          });
      }

      function groupByColumn(filteredRules) {
        const grouped = new Map();
        filteredRules.forEach((rule) => {
          const column = clean(rule.target_column) || "(unmapped)";
          if (!grouped.has(column)) grouped.set(column, []);
          grouped.get(column).push(rule);
        });

        return Array.from(grouped.entries())
          .sort((a, b) => a[0].localeCompare(b[0], undefined, { sensitivity: "base" }))
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
            tdType.textContent = clean(rule.test_type) || "—";

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
          window.location.hash = href;
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

async function runValidation() {
  const button = document.getElementById("runValidation");
  const clearButton = document.getElementById("clearTable");
  const backendUrl = CONFIG.BACKEND_URL;
  const maxCellsPerChunk = CONFIG.MAX_CELLS_PER_CHUNK;

  // Get the selected test pack from dropdown
  const selectedPack = String(document.getElementById("testPacks").value || "").trim().toLowerCase();
  const testPacks = [selectedPack];
  const packConfigEditor = document.getElementById("packConfigs");
  let selectedPackConfig;
  try {
    selectedPackConfig = parsePackConfigInput(packConfigEditor.value, selectedPack);
  } catch {
    setStatus("Pack configs JSON is invalid.", true);
    return;
  }

  const normalizedConfig = withDefaultEnabledTests(
    { [selectedPack]: selectedPackConfig },
    selectedPack
  )[selectedPack];
  const selectedTerritory = getSelectedTerritoryValue();
  if (selectedTerritory) {
    normalizedConfig.territory = selectedTerritory;
  } else {
    delete normalizedConfig.territory;
  }
  packConfigsByPack[selectedPack] = normalizedConfig;
  currentPackSelection = selectedPack;
  packConfigEditor.value = JSON.stringify(normalizedConfig, null, 2);
  const packConfigs = { [selectedPack]: normalizedConfig };

  const excelUserEmail = getExcelUserEmail();
  if (!excelUserEmail) {
    setStatus("Validation failed: Could not determine Excel user email.", true);
    return;
  }

  button.disabled = true;
  setStatus("Detecting table on active sheet...");

  try {
    const selectionMeta = await resolveValidationRangeMeta();
    lastValidationSourceSheetName = selectionMeta.sheetName || null;
    lastValidationExecutedTests = [];
    lastValidationResults = [];
    lastValidationPack = selectedPack;

    if (clearButton) {
      clearButton.disabled = true;
    }

    const dataRowCount = selectionMeta.rowCount - 1;
    const rowsPerChunk = Math.max(1, Math.floor(maxCellsPerChunk / selectionMeta.columnCount));
    const totalChunks = Math.ceil(dataRowCount / rowsPerChunk);

    const targetDescription = selectionMeta.source === "selection" ? "selected range" : "detected table";
    setStatus(`Clearing existing comments in ${targetDescription}...`);
    await clearCommentsInRange(
      selectionMeta.startRow,
      selectionMeta.startCol,
      selectionMeta.rowCount,
      selectionMeta.columnCount
    );

    let failedCount = 0;
    const aggregatedResults = [];
    const executedTestNames = new Set();
    const coverageWarnings = new Set();

    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
      const chunkDataStartOffset = chunkIndex * rowsPerChunk;
      const currentDataRows = Math.min(rowsPerChunk, dataRowCount - chunkDataStartOffset);
      const chunkStartRow = selectionMeta.startRow + 1 + chunkDataStartOffset;

      setStatus(`Validating chunk ${chunkIndex + 1}/${totalChunks}...`);
      const chunkValues = await readRangeValues(
        chunkStartRow,
        selectionMeta.startCol,
        currentDataRows,
        selectionMeta.columnCount
      );

      const chunkAddresses = [];
      for (let rowOffset = 0; rowOffset < currentDataRows; rowOffset += 1) {
        chunkAddresses.push(
          buildAddressRow(chunkStartRow + rowOffset, selectionMeta.startCol, selectionMeta.columnCount)
        );
      }

      const payloadAddresses = [selectionMeta.headerAddresses, ...chunkAddresses];
      const payloadValues = [selectionMeta.headerValues, ...chunkValues];
      const workbookName = getWorkbookName();

      const response = await fetch(`${backendUrl}/validate-range`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Excel-User-Email": excelUserEmail,
        },
        body: JSON.stringify({
          addresses: payloadAddresses,
          values: payloadValues,
          testPacks,
          hasHeaderRow: true,
          packConfigs,
          includeCoverage: true,
          workbookName,
          sheetName: selectionMeta.sheetName || null,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        let errorData = {};
        if (errorText) {
          try {
            errorData = JSON.parse(errorText);
          } catch {
            errorData = { detail: errorText };
          }
        }

        const detail = formatBackendErrorDetail(errorData.detail) || `HTTP ${response.status}`;
        throw new Error(detail);
      }

      const data = await response.json();
      const results = data.results || [];
      aggregatedResults.push(...results);
      // Use severityScore for heatmap scaling (falls back to failCount for compatibility)
      const maxSeverityScore = Math.max(
        ...results.map((result) => result.severityScore !== undefined ? result.severityScore : result.failCount || 0),
        1
      );

      const coveragePacks = data?.coverage?.packs || {};
      for (const [packName, packCoverage] of Object.entries(coveragePacks)) {
        if (packCoverage?.warning) {
          coverageWarnings.add(`${packName}: ${packCoverage.warning}`);
        }
        if (Array.isArray(packCoverage?.warnings)) {
          for (const warning of packCoverage.warnings) {
            coverageWarnings.add(`${packName}: ${warning}`);
          }
        }
        const tests = packCoverage?.tests || {};
        for (const testName of Object.keys(tests)) {
          executedTestNames.add(`${packName}.${testName}`);
        }
      }

      setStatus(`Applying results for chunk ${chunkIndex + 1}/${totalChunks}...`);
      await applyResultsToSheet(results, maxSeverityScore);

      failedCount += results.filter((item) => item.rowIndex > 0 && item.failCount > 0).length;
    }

    const packName = testPacks[0];
    lastValidationResults = aggregatedResults;
    lastValidationExecutedTests = Array.from(executedTestNames).sort();
    const warningText = Array.from(coverageWarnings).join(" | ");
    const statusMessage = `Validation complete with ${packName}: ${failedCount} cells failed at least one test.`;
    setStatus(warningText ? `${statusMessage} Warning: ${warningText}.` : statusMessage, Boolean(warningText));
  } catch (error) {
    const message = error?.message || "Unexpected error";

    if (/Failed to fetch/i.test(message)) {
      const diagnostic = await getDevelopmentFetchDiagnostics(backendUrl);
      setStatus(`Validation failed: ${message}. ${diagnostic}`, true);
    } else {
      setStatus(`Validation failed: ${message}`, true);
    }
  } finally {
    button.disabled = false;
    if (clearButton) {
      clearButton.disabled = false;
    }
    // Update Extract / Visualise state based on whether there are results
    try { updateActionButtons(); } catch (e) { /* ignore */ }
  }
}
