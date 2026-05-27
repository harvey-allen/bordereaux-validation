/**
 * Heatmap color gradient: no failures=white, then level 1-10 as light→dark red.
 * Uses severity score instead of simple failure count for more nuanced coloring.
 * Severity levels: INFO=0, WARNING=1, ERROR=2, CRITICAL=3
 */
const packDefaultTests = {
  premium: ["Bpolicy_id1", "Bcurrency1", "Bpremium_amount1"],
  claims: ["Bpolicy_id1", "Bcurrency1", "Bclaim_amount1"],
};

const DEFAULT_EXCEL_EMAIL = "harveyallen2001@gmail.com";
let packConfigsByPack = {};
let currentPackSelection = null;
let territoriesByPack = {};

function getDefaultPackConfig(selectedPack) {
  const normalizedPack = String(selectedPack || "").trim().toLowerCase();
  return {
    testPack: normalizedPack,
    UMR: "Unique Market Reference (UMR)",
    enabledTests: [...(packDefaultTests[normalizedPack] || [])],
  };
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
  const configuredTests = existingPackConfig.enabledTests;
  const hasConfiguredTests = Array.isArray(configuredTests) && configuredTests.length > 0;

  if (!hasConfiguredTests) {
    existingPackConfig.enabledTests = [...(packDefaultTests[normalizedPack] || [])];
  }

  nextConfigs[normalizedPack] = existingPackConfig;
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
    return nestedConfig;
  }

  return directConfig;
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
  testPackSelect.value = CONFIG.DEFAULT_PACK;
  if (!testPackSelect.value) {
    testPackSelect.value = "premium";
  }
  packConfigsByPack = {
    premium: getDefaultPackConfig("premium"),
    claims: getDefaultPackConfig("claims"),
  };
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
  }
}
