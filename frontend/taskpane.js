/**
 * Heatmap color gradient: light green (0 severity) → dark red (max severity)
 * Uses severity score instead of simple failure count for more nuanced coloring.
 * Severity levels: INFO=1, WARNING=2, ERROR=3, CRITICAL=5
 */
const packDefaultTests = {
  bordereaux: [],
};

function heatmapColor(severityScore, maxSeverityScore) {
  const startRed = 226, startGreen = 240, startBlue = 217;
  const endRed = 192, endGreen = 0, endBlue = 0;
  const failScaleCap = CONFIG.HEATMAP_FAIL_CAP;

  const _maxSeverityScore = maxSeverityScore;
  void _maxSeverityScore;
  const clampedScore = Math.max(0, Math.min(failScaleCap, Number(severityScore) || 0));
  const ratio = clampedScore / failScaleCap;

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

function syncPackConfigEditorWithSelectedPack() {
  const selectedPack = document.getElementById("testPacks").value;
  const packConfigEditor = document.getElementById("packConfigs");

  let packConfigs;
  try {
    packConfigs = JSON.parse(packConfigEditor.value || "{}");
  } catch {
    return;
  }

  const normalizedPack = String(selectedPack || "").trim().toLowerCase();
  const updatedPackConfigs = withDefaultEnabledTests(packConfigs, normalizedPack);
  packConfigEditor.value = JSON.stringify(updatedPackConfigs, null, 2);
}

/**
 * Get or create API key for the current Excel user.
 * Stores the key in localStorage for persistence.
 * 
 * For Excel add-ins, we use Office.context.document.url combined with
 * a user-provided email or auto-generated ID since Excel doesn't provide
 * user identity directly like Outlook does.
 */
async function ensureApiKey() {
  // Check if we already have a stored API key
  let apiKey = localStorage.getItem("bordereaux_api_key");
  if (apiKey) {
    return apiKey;
  }

  // Use the development key from config as fallback
  if (CONFIG.API_KEY) {
    return CONFIG.API_KEY;
  }

  // Try to register with the backend
  try {
    // Generate a unique Excel user ID based on the add-in context
    // This persists per-user via localStorage partitioning
    let excelUserId = localStorage.getItem("bordereaux_user_id");
    if (!excelUserId) {
      // Generate unique ID for this user/machine combination
      const partitionKey = Office.context.partitionKey || "";
      const timestamp = Date.now();
      const random = Math.random().toString(36).substring(2, 10);
      excelUserId = `excel_${partitionKey}_${timestamp}_${random}`;
      localStorage.setItem("bordereaux_user_id", excelUserId);
    }

    // Try to get user email - prompt if needed for production
    let email = localStorage.getItem("bordereaux_user_email");
    if (!email) {
      // For now, use a placeholder - could show a dialog to collect this
      email = `${excelUserId}@bordereaux.local`;
    }

    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        excel_user_id: excelUserId,
        email: email,
        display_name: null,
      }),
    });

    if (response.ok) {
      const data = await response.json();
      if (data.api_key) {
        // Store the new API key
        localStorage.setItem("bordereaux_api_key", data.api_key);
        console.log("New API key registered and stored");
        return data.api_key;
      }
    }
  } catch (error) {
    console.warn("Could not register with backend:", error);
  }

  // Fall back to dev key
  return CONFIG.API_KEY;
}

/**
 * Get the API key to use for requests.
 */
function getApiKey() {
  return localStorage.getItem("bordereaux_api_key") || CONFIG.API_KEY;
}

/**
 * Update the user info display in the UI.
 */
function updateUserInfoDisplay() {
  const userInfo = document.getElementById("userInfo");
  const emailInput = document.getElementById("userEmail");
  
  const storedEmail = localStorage.getItem("bordereaux_user_email");
  const storedApiKey = localStorage.getItem("bordereaux_api_key");
  const storedUserId = localStorage.getItem("bordereaux_user_id");
  
  if (emailInput && storedEmail) {
    emailInput.value = storedEmail;
  }
  
  if (userInfo) {
    if (storedApiKey && storedEmail) {
      userInfo.innerHTML = `Registered as <strong>${storedEmail}</strong><br/>API Key: ${storedApiKey.substring(0, 12)}...`;
    } else if (storedApiKey) {
      userInfo.innerHTML = `Using API key: ${storedApiKey.substring(0, 12)}...<br/>ID: ${storedUserId || 'dev'}`;
    } else {
      userInfo.textContent = "Not Registered - Using Development Key";
    }
  }
}

/**
 * Register the user with the backend using their email.
 */
async function registerUser() {
  const emailInput = document.getElementById("userEmail");
  const email = emailInput?.value?.trim();
  
  if (!email || !email.includes("@")) {
    setStatus("Please enter a valid email address", true);
    return;
  }
  
  setStatus("Registering...");
  
  try {
    // Generate or use existing user ID
    let excelUserId = localStorage.getItem("bordereaux_user_id");
    if (!excelUserId) {
      const partitionKey = Office.context.partitionKey || "";
      const timestamp = Date.now();
      const random = Math.random().toString(36).substring(2, 10);
      excelUserId = `excel_${partitionKey}_${timestamp}_${random}`;
      localStorage.setItem("bordereaux_user_id", excelUserId);
    }
    
    // Clear existing API key to force new registration
    localStorage.removeItem("bordereaux_api_key");
    
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        excel_user_id: excelUserId,
        email: email,
        display_name: null,
      }),
    });
    
    if (response.ok) {
      const data = await response.json();
      if (data.api_key) {
        localStorage.setItem("bordereaux_api_key", data.api_key);
        localStorage.setItem("bordereaux_user_email", email);
        setStatus(`Registered successfully! Tier: ${data.tier || 'TRIAL'}`);
        updateUserInfoDisplay();
      }
    } else {
      const error = await response.json();
      setStatus(`Registration failed: ${error.detail || 'Unknown error'}`, true);
    }
  } catch (error) {
    console.error("Registration error:", error);
    setStatus(`Registration failed: ${error.message}`, true);
  }
}

Office.onReady(async () => {
  const initialPackConfigs = withDefaultEnabledTests(
    {
      bordereaux: {
        RefColumn: CONFIG.DEFAULT_REF_COLUMN,
      }
    },
    CONFIG.DEFAULT_PACK
  );

  document.getElementById("packConfigs").value = JSON.stringify(initialPackConfigs, null, 2);
  document.getElementById("testPacks").value = CONFIG.DEFAULT_PACK;
  document.getElementById("testPacks").addEventListener("change", syncPackConfigEditorWithSelectedPack);
  document.getElementById("runValidation").addEventListener("click", runValidation);
  
  // User registration
  document.getElementById("saveEmail")?.addEventListener("click", registerUser);

  // Try to ensure we have an API key
  try {
    await ensureApiKey();
  } catch (error) {
    console.warn("Could not ensure API key:", error);
  }
  
  // Update user info display
  updateUserInfoDisplay();
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
      if (result.rowIndex === 0) {
        continue;
      }

      const cell = worksheet.getRange(result.address);
      // Use severityScore for heatmap coloring (falls back to failCount for compatibility)
      const severityScore = result.severityScore !== undefined ? result.severityScore : result.failCount;
      const color = heatmapColor(severityScore, maxSeverityScore);
      cell.format.fill.color = color;

      if (result.failCount > 0) {
        cellsWithFailures.push({ address: result.address, comment: result.comment });
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
  const backendUrl = CONFIG.BACKEND_URL;
  const maxCellsPerChunk = CONFIG.MAX_CELLS_PER_CHUNK;

  let packConfigs;
  try {
    packConfigs = JSON.parse(document.getElementById("packConfigs").value);
  } catch {
    setStatus("Pack configs JSON is invalid.", true);
    return;
  }

  // Get the selected test pack from dropdown
  const selectedPack = String(document.getElementById("testPacks").value || "").trim().toLowerCase();
  const testPacks = [selectedPack];
  packConfigs = withDefaultEnabledTests(packConfigs, selectedPack);
  document.getElementById("packConfigs").value = JSON.stringify(packConfigs, null, 2);

  button.disabled = true;
  setStatus("Reading selected range from Excel...");

  try {
    const selectionMeta = await Excel.run(async (context) => {
      const workbook = context.workbook;
      const worksheet = workbook.worksheets.getActiveWorksheet();
      const selectedRange = workbook.getSelectedRange();

      selectedRange.load(["rowIndex", "columnIndex", "rowCount", "columnCount"]);
      await context.sync();

      const headerRange = worksheet.getRangeByIndexes(
        selectedRange.rowIndex,
        selectedRange.columnIndex,
        1,
        selectedRange.columnCount
      );
      headerRange.load("values");

      await context.sync();

      return {
        startRow: selectedRange.rowIndex,
        startCol: selectedRange.columnIndex,
        rowCount: selectedRange.rowCount,
        columnCount: selectedRange.columnCount,
        headerValues: headerRange.values[0],
        headerAddresses: buildAddressRow(
          selectedRange.rowIndex,
          selectedRange.columnIndex,
          selectedRange.columnCount
        ),
      };
    });

    if (selectionMeta.rowCount < 2) {
      throw new Error("Please select a range that includes a header row and at least one data row.");
    }

    const dataRowCount = selectionMeta.rowCount - 1;
    const rowsPerChunk = Math.max(1, Math.floor(maxCellsPerChunk / selectionMeta.columnCount));
    const totalChunks = Math.ceil(dataRowCount / rowsPerChunk);

    setStatus("Clearing existing comments in selected range...");
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

      const response = await fetch(`${backendUrl}/validate-range`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": getApiKey(),
        },
        body: JSON.stringify({
          addresses: payloadAddresses,
          values: payloadValues,
          testPacks,
          hasHeaderRow: true,
          packConfigs,
          includeCoverage: true,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const detail = errorData.detail || `HTTP ${response.status}`;
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
    setStatus(`Validation failed: ${message}`, true);
  } finally {
    button.disabled = false;
  }
}
