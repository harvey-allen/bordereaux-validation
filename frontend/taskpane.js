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
let lastValidationFailedTests = [];
let lastValidationPassedTests = [];
let lastValidationPassedUmrs = [];
let lastTaggedCells = [];
let savedResultsVersionExists = false;
let savedResultsVersionCreatedAt = null;
let savedVersionItems = [];
let activeViewedVersionContext = null;
const APP_LOGO_URL = `${window.location.origin}/AXIOS.png`;
const EXCEPTION_TAG_FILL = "#dbeafe";
const MAX_EXCEL_SHEET_NAME_LENGTH = 31;
const DEBUG_LOG_STORAGE_KEY = "bordereaux_validator_debug_log";
const VIEWED_VERSION_CONTEXT_STORAGE_KEY = "bordereaux_validator_viewed_version_context";
const PACK_CONFIG_STATE_STORAGE_KEY = "bordereaux_validator_pack_config_state";

let availablePackOptions = [];
let currentSheetPackConfigScope = null;
let packConfigInputPersistTimer = null;
let activeSheetSyncSequence = 0;

const {
  formatPackLabel,
  formatTestTypeLabel,
  populatePackSelect,
  loadSubscribedPackValues,
} = window.TaskpanePacks || {};

const storageHelpers = window.TaskpaneStorage || {};

function appendDebugLog(message, metadata = null) {
  try {
    const entry = {
      at: new Date().toISOString(),
      message: String(message || ""),
      metadata: metadata && typeof metadata === "object" ? metadata : null,
    };
    const existing = JSON.parse(localStorage.getItem(DEBUG_LOG_STORAGE_KEY) || "[]");
    const next = Array.isArray(existing) ? existing : [];
    next.push(entry);
    const trimmed = next.slice(-200);
    localStorage.setItem(DEBUG_LOG_STORAGE_KEY, JSON.stringify(trimmed));
    if (entry.metadata) {
      console.log("[BV-DEBUG]", entry.message, entry.metadata);
    } else {
      console.log("[BV-DEBUG]", entry.message);
    }
  } catch {
    // best-effort logging only
  }
}

function buildSheetScopeKey(workbookName, sheetName) {
  const wb = String(workbookName || "__unknown_workbook__").trim() || "__unknown_workbook__";
  const sh = String(sheetName || "__unknown_sheet__").trim() || "__unknown_sheet__";
  return `${wb}::${sh}`;
}

function ensureStatusElement() {
  let status = document.getElementById("status");
  if (status || !document.body) {
    return status;
  }

  status = document.createElement("div");
  status.id = "status";
  status.className = "status";
  document.body.appendChild(status);
  return status;
}

function buildFrontendErrorMessage(prefix, error) {
  const detail = error instanceof Error
    ? error.message
    : String(error?.message || error || "Unexpected error");
  return `${prefix}: ${detail}`;
}

function shouldSuppressFrontendError(error) {
  const message = String(error?.message || error || "").toLowerCase();
  return message.includes("invalid api call in the current context");
}

function reportFrontendError(prefix, error, options = {}) {
  appendDebugLog(prefix, {
    message: String(error?.message || error || "Unexpected error"),
    stack: String(error?.stack || ""),
  });

  if (shouldSuppressFrontendError(error)) {
    return;
  }

  if (options.showStatus === false) {
    return;
  }

  setStatus(buildFrontendErrorMessage(prefix, error), true);
}

function installGlobalFrontendErrorHandlers() {
  if (window.__bvGlobalErrorHandlersInstalled) {
    return;
  }

  window.__bvGlobalErrorHandlersInstalled = true;

  window.addEventListener("error", (event) => {
    reportFrontendError("Frontend error", event?.error || event?.message || "Unexpected error");
  });

  window.addEventListener("unhandledrejection", (event) => {
    reportFrontendError("Unhandled frontend error", event?.reason || "Unexpected error");
  });
}

async function closeTaskpaneIfSupported() {
  try {
    if (typeof Office?.addin?.hide === "function") {
      await Office.addin.hide();
    }
  } catch {
    // Best effort only.
  }
}

function getAvailablePackValues() {
  if (Array.isArray(availablePackOptions) && availablePackOptions.length > 0) {
    return availablePackOptions;
  }

  const select = document.getElementById("testPacks");
  const optionValues = Array.from(select?.options || [])
    .map((option) => String(option.value || "").trim().toLowerCase())
    .filter(Boolean);

  return optionValues.length > 0 ? optionValues : ["risk_and_premium"];
}

function buildDefaultPackConfigs(packValues = getAvailablePackValues()) {
  return Object.fromEntries(
    packValues.map((packName) => [packName, getDefaultPackConfig(packName)])
  );
}

function normalizePackConfigsByPack(rawPackConfigs) {
  const normalized = buildDefaultPackConfigs();
  const source = rawPackConfigs && typeof rawPackConfigs === "object" && !Array.isArray(rawPackConfigs)
    ? rawPackConfigs
    : {};

  for (const [rawPackName, rawConfig] of Object.entries(source)) {
    const packName = String(rawPackName || "").trim().toLowerCase();
    if (!packName) {
      continue;
    }

    const defaultConfig = normalized[packName] || getDefaultPackConfig(packName);
    normalized[packName] = withDefaultEnabledTests(
      {
        [packName]: normalizePackConfigShape(
          {
            ...defaultConfig,
            ...(rawConfig && typeof rawConfig === "object" && !Array.isArray(rawConfig) ? rawConfig : {}),
          },
          packName
        ),
      },
      packName
    )[packName];
  }

  return normalized;
}

function getSafePackSelection(preferredPack) {
  const availablePacks = getAvailablePackValues();
  const normalizedPreferredPack = String(preferredPack || "").trim().toLowerCase();
  if (normalizedPreferredPack && availablePacks.includes(normalizedPreferredPack)) {
    return normalizedPreferredPack;
  }
  return availablePacks[0] || "risk_and_premium";
}

function getPackConfigStateMap() {
  try {
    const raw = localStorage.getItem(PACK_CONFIG_STATE_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch {
    // ignore
  }
  return {};
}

function setPackConfigStateMap(nextStateMap) {
  try {
    const payload = nextStateMap && typeof nextStateMap === "object" && !Array.isArray(nextStateMap)
      ? nextStateMap
      : {};
    localStorage.setItem(PACK_CONFIG_STATE_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // ignore
  }
}

function getStoredPackConfigStateForSheet(workbookName, sheetName) {
  const key = buildSheetScopeKey(workbookName, sheetName);
  const entry = getPackConfigStateMap()[key];
  if (!entry || typeof entry !== "object") {
    return null;
  }

  return {
    selectedPack: getSafePackSelection(entry.selectedPack),
    packConfigsByPack: normalizePackConfigsByPack(entry.packConfigsByPack),
  };
}

function storePackConfigStateForSheet(workbookName, sheetName, state) {
  const key = buildSheetScopeKey(workbookName, sheetName);
  const nextStateMap = getPackConfigStateMap();
  nextStateMap[key] = {
    selectedPack: getSafePackSelection(state?.selectedPack),
    packConfigsByPack: normalizePackConfigsByPack(state?.packConfigsByPack),
    updatedAt: new Date().toISOString(),
  };
  setPackConfigStateMap(nextStateMap);
}

async function resolveSheetPackConfigScope() {
  const workbookName = getWorkbookName() || "__unknown_workbook__";
  const sheetName = String(await getActiveSheetName() || "__unknown_sheet__").trim() || "__unknown_sheet__";
  return {
    workbookName,
    sheetName,
    key: buildSheetScopeKey(workbookName, sheetName),
  };
}

function snapshotPackConfigStateFromUi() {
  const selectedPack = getSafePackSelection(
    document.getElementById("testPacks")?.value || currentPackSelection || getAvailablePackValues()[0]
  );
  const nextPackConfigs = normalizePackConfigsByPack(packConfigsByPack);
  const packConfigEditor = document.getElementById("packConfigs");
  let isEditorValid = true;
  let validationError = null;

  if (selectedPack && packConfigEditor) {
    try {
      const parsedConfig = parsePackConfigInput(packConfigEditor.value, selectedPack);
      const selectedTerritory = getSelectedTerritoryValue();
      if (selectedTerritory) {
        parsedConfig.territory = selectedTerritory;
      } else {
        delete parsedConfig.territory;
      }
      nextPackConfigs[selectedPack] = withDefaultEnabledTests({ [selectedPack]: parsedConfig }, selectedPack)[selectedPack];
    } catch (error) {
      isEditorValid = false;
      validationError = error;
    }
  }

  return {
    selectedPack,
    packConfigsByPack: nextPackConfigs,
    isEditorValid,
    validationError,
  };
}

async function persistPackConfigStateForScope(options = {}) {
  const scope = options.scope || currentSheetPackConfigScope;
  if (!scope?.sheetName) {
    return null;
  }

  const snapshot = snapshotPackConfigStateFromUi();
  currentPackSelection = snapshot.selectedPack;
  packConfigsByPack = snapshot.packConfigsByPack;
  storePackConfigStateForSheet(scope.workbookName, scope.sheetName, snapshot);

  if (options.persistToServer && snapshot.isEditorValid && snapshot.selectedPack) {
    await persistPackConfigurationForSheet(
      snapshot.selectedPack,
      snapshot.packConfigsByPack[snapshot.selectedPack],
      scope.sheetName
    );
  }

  if (!snapshot.isEditorValid && options.showValidationError) {
    setStatus("Pack configs JSON is invalid.", true);
  }

  return snapshot;
}

function applyPackConfigStateToUi(state) {
  const testPackSelect = document.getElementById("testPacks");
  const nextState = state || {
    selectedPack: getSafePackSelection(testPackSelect?.value || currentPackSelection),
    packConfigsByPack: buildDefaultPackConfigs(),
  };
  const selectedPack = getSafePackSelection(nextState.selectedPack);

  // Preserve existing pack configurations when switching sheets (retain aliases and other settings)
  // Only merge in defaults for packs that aren't already configured
  const preservedConfigs = { ...packConfigsByPack };
  packConfigsByPack = normalizePackConfigsByPack(nextState.packConfigsByPack);
  
  // Restore previously configured aliases and settings
  for (const [packName, config] of Object.entries(preservedConfigs)) {
    if (config?.aliases && !packConfigsByPack[packName]?.aliases) {
      packConfigsByPack[packName].aliases = config.aliases;
    }
    if (config?.enabledTests && !packConfigsByPack[packName]?.enabledTests) {
      packConfigsByPack[packName].enabledTests = config.enabledTests;
    }
  }
  
  currentPackSelection = selectedPack;

  if (testPackSelect) {
    testPackSelect.value = selectedPack;
    if (!testPackSelect.value) {
      testPackSelect.value = getSafePackSelection(selectedPack);
      currentPackSelection = String(testPackSelect.value || currentPackSelection || "").trim().toLowerCase();
    }
  }

  renderSelectedPackConfig(currentPackSelection);
}

function schedulePackConfigStatePersist(options = {}) {
  if (packConfigInputPersistTimer) {
    window.clearTimeout(packConfigInputPersistTimer);
  }

  const delayMs = Number(options.delayMs);
  const effectiveDelay = Number.isFinite(delayMs) ? delayMs : 450;

  packConfigInputPersistTimer = window.setTimeout(() => {
    persistPackConfigStateForScope({
      persistToServer: Boolean(options.persistToServer),
      showValidationError: Boolean(options.showValidationError),
    }).catch((error) => {
      reportFrontendError("Pack config save failed", error, { showStatus: Boolean(options.showSaveError) });
    });
  }, Math.max(0, effectiveDelay));
}

async function syncPackConfigStateWithActiveSheet(options = {}) {
  const syncSequence = ++activeSheetSyncSequence;

  if (!options.skipSavePreviousSheet && currentSheetPackConfigScope?.sheetName) {
    try {
      await persistPackConfigStateForScope({
        scope: currentSheetPackConfigScope,
        persistToServer: true,
        showValidationError: false,
      });
    } catch (error) {
      reportFrontendError("Could not save the previous sheet configuration", error, { showStatus: false });
    }
  }

  const nextScope = await resolveSheetPackConfigScope();
  if (syncSequence !== activeSheetSyncSequence) {
    return;
  }

  currentSheetPackConfigScope = nextScope;
  const storedState = getStoredPackConfigStateForSheet(nextScope.workbookName, nextScope.sheetName);
  applyPackConfigStateToUi(storedState);
  await syncTerritorySelectorForSelectedPack();

  try {
    await hydrateSelectedPackConfigFromServer({
      workbookName: nextScope.workbookName,
      sheetName: nextScope.sheetName,
    });
  } catch (error) {
    reportFrontendError("Could not load sheet-specific pack configuration", error, { showStatus: false });
  }

  if (syncSequence !== activeSheetSyncSequence) {
    return;
  }

  storePackConfigStateForSheet(nextScope.workbookName, nextScope.sheetName, {
    selectedPack: currentPackSelection,
    packConfigsByPack,
  });

  await syncTerritorySelectorForSelectedPack();
  await refreshVersionStateForActiveSheet();

  if (document.getElementById("exceptionModal")?.classList.contains("active")) {
    await loadLinkedFieldsForExceptionModal();
  }
}

function getViewedVersionContextMap() {
  try {
    const raw = localStorage.getItem(VIEWED_VERSION_CONTEXT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch {
    // ignore
  }
  return {};
}

function setViewedVersionContextMap(contextMap) {
  try {
    const payload = contextMap && typeof contextMap === "object" && !Array.isArray(contextMap)
      ? contextMap
      : {};
    localStorage.setItem(VIEWED_VERSION_CONTEXT_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // ignore
  }
}

function setViewedVersionContextForSheet(context) {
  const workbookName = String(context?.workbookName || "").trim() || "__unknown_workbook__";
  const sheetName = String(context?.sheetName || "").trim() || "__unknown_sheet__";
  const versionId = Number(context?.versionId || 0);
  const testPack = String(context?.testPack || "").trim().toLowerCase();

  if (!versionId || !testPack) {
    return;
  }

  const map = getViewedVersionContextMap();
  const key = buildSheetScopeKey(workbookName, sheetName);
  map[key] = {
    workbookName,
    sheetName,
    versionId,
    sheetKeyId: Number(context?.sheetKeyId || 0) || null,
    testPack,
    versionName: String(context?.versionName || "").trim() || null,
    createdAt: new Date().toISOString(),
  };
  setViewedVersionContextMap(map);
}

function getViewedVersionContextForSheet(workbookName, sheetName) {
  const map = getViewedVersionContextMap();
  const key = buildSheetScopeKey(workbookName, sheetName);
  const context = map[key];
  if (!context || typeof context !== "object") {
    return null;
  }
  const versionId = Number(context.versionId || 0);
  const testPack = String(context.testPack || "").trim().toLowerCase();
  if (!versionId || !testPack) {
    return null;
  }
  return {
    workbookName: String(context.workbookName || workbookName || "").trim() || "__unknown_workbook__",
    sheetName: String(context.sheetName || sheetName || "").trim() || "__unknown_sheet__",
    versionId,
    sheetKeyId: Number(context.sheetKeyId || 0) || null,
    testPack,
    versionName: String(context.versionName || "").trim() || null,
    createdAt: String(context.createdAt || "").trim() || null,
  };
}

function removeViewedVersionContextByVersionId(versionId) {
  const normalizedVersionId = Number(versionId || 0);
  if (!normalizedVersionId) {
    return;
  }
  const map = getViewedVersionContextMap();
  let changed = false;
  for (const [key, value] of Object.entries(map)) {
    if (Number(value?.versionId || 0) === normalizedVersionId) {
      delete map[key];
      changed = true;
    }
  }
  if (changed) {
    setViewedVersionContextMap(map);
  }
}

async function refreshActiveViewedVersionContext() {
  const workbookName = getWorkbookName() || "__unknown_workbook__";
  const activeSheetName = await getActiveSheetName();
  const sheetName = String(activeSheetName || "__unknown_sheet__").trim() || "__unknown_sheet__";
  activeViewedVersionContext = getViewedVersionContextForSheet(workbookName, sheetName);
}

window.__bvGetDebugLogs = function __bvGetDebugLogs() {
  try {
    return JSON.parse(localStorage.getItem(DEBUG_LOG_STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
};

window.__bvClearDebugLogs = function __bvClearDebugLogs() {
  try {
    localStorage.removeItem(DEBUG_LOG_STORAGE_KEY);
  } catch {
    // ignore
  }
};

/**
 * Persist all validation results to localStorage
 */
function persistValidationResults() {
  if (typeof storageHelpers.persist !== "function") {
    return;
  }
  storageHelpers.persist({
    results: lastValidationResults,
    sourceSheetName: lastValidationSourceSheetName,
    executedTests: lastValidationExecutedTests,
    pack: lastValidationPack,
    failedTests: lastValidationFailedTests,
    passedTests: lastValidationPassedTests,
    passedUmrs: lastValidationPassedUmrs,
    taggedCells: lastTaggedCells,
  });
}

/**
 * Restore validation results from localStorage
 */
function restoreValidationResults() {
  if (typeof storageHelpers.restore !== "function") {
    return false;
  }
  const persistData = storageHelpers.restore();
  if (!persistData) {
    return false;
  }
  lastValidationResults = Array.isArray(persistData.results) ? persistData.results : [];
  lastValidationSourceSheetName = persistData.sourceSheetName || null;
  lastValidationExecutedTests = Array.isArray(persistData.executedTests) ? persistData.executedTests : [];
  lastValidationPack = persistData.pack || null;
  lastValidationFailedTests = Array.isArray(persistData.failedTests) ? persistData.failedTests : [];
  lastValidationPassedTests = Array.isArray(persistData.passedTests) ? persistData.passedTests : [];
  lastValidationPassedUmrs = Array.isArray(persistData.passedUmrs) ? persistData.passedUmrs : [];
  lastTaggedCells = Array.isArray(persistData.taggedCells) ? persistData.taggedCells : [];
  return true;
}

/**
 * Clear persisted validation results from localStorage
 */
function clearPersistedValidationResults() {
  if (typeof storageHelpers.clear !== "function") {
    return;
  }
  storageHelpers.clear();
}

function normalizeTaggedCellRecord(item) {
  if (!item || typeof item !== "object") {
    return null;
  }

  const address = String(item.address || "").trim().toUpperCase();
  const exceptionId = String(item.exception_id || item.exceptionId || "").trim();
  if (!address || !exceptionId) {
    return null;
  }

  return {
    address,
    exception_id: exceptionId,
    comment: String(item.comment || `Exception tagged: ${exceptionId}`).trim(),
    fill_color: String(item.fill_color || item.fillColor || EXCEPTION_TAG_FILL).trim() || EXCEPTION_TAG_FILL,
    previous_fill_color: String(item.previous_fill_color || item.previousFillColor || "").trim(),
    sheet_name: String(item.sheet_name || item.sheetName || "").trim(),
    workbook_name: String(item.workbook_name || item.workbookName || "").trim(),
    tagged_at: String(item.tagged_at || item.taggedAt || new Date().toISOString()).trim(),
  };
}

function mergeTaggedCells(existingItems, incomingItems) {
  const merged = new Map();
  for (const rawItem of existingItems || []) {
    const item = normalizeTaggedCellRecord(rawItem);
    if (!item) {
      continue;
    }
    merged.set(`${item.workbook_name}::${item.sheet_name}::${item.address}`, item);
  }
  for (const rawItem of incomingItems || []) {
    const item = normalizeTaggedCellRecord(rawItem);
    if (!item) {
      continue;
    }
    merged.set(`${item.workbook_name}::${item.sheet_name}::${item.address}`, item);
  }
  return Array.from(merged.values());
}

function getTaggedCellsForScope(workbookName, sheetName) {
  const normalizedWorkbook = String(workbookName || "").trim();
  const normalizedSheet = String(sheetName || "").trim();
  return (lastTaggedCells || []).filter((item) => {
    const taggedCell = normalizeTaggedCellRecord(item);
    return taggedCell
      && taggedCell.workbook_name === normalizedWorkbook
      && taggedCell.sheet_name === normalizedSheet;
  });
}
const SANKEY_EXPORT_WIDTH = 1800;
const SANKEY_EXPORT_HEIGHT = 330;
const SANKEY_DISPLAY_WIDTH = 1250;
const SANKEY_DISPLAY_HEIGHT = Math.round((SANKEY_EXPORT_HEIGHT / SANKEY_EXPORT_WIDTH) * SANKEY_DISPLAY_WIDTH);

function updateActionButtons() {
  const extractButton = document.getElementById("extractResults");
  const visualiseButton = document.getElementById("visualiseResults");
  const saveButton = document.getElementById("saveResultsVersion");
  const deleteButton = document.getElementById("deleteResultsVersion");
  const viewButton = document.getElementById("viewSavedVersion");
  const savedVersions = document.getElementById("savedVersions");
  const hasResults = Array.isArray(lastValidationResults) && lastValidationResults.length > 0;
  const hasSavedVersionSelection = Boolean(savedVersions && savedVersions.value);
  const selectedSavedVersion = getSelectedSavedVersionItem();
  const canViewSavedVersion = Boolean(
    selectedSavedVersion
    && !Boolean(selectedSavedVersion.current_scope || selectedSavedVersion.currentScope)
  );
  if (extractButton) extractButton.disabled = !hasResults;
  if (visualiseButton) visualiseButton.disabled = !hasResults;
  if (saveButton) saveButton.disabled = !hasResults;
  if (deleteButton) deleteButton.disabled = !hasSavedVersionSelection;
  if (viewButton) viewButton.disabled = !canViewSavedVersion;
}

function updateSaveButtonLabel() {
  const saveButton = document.getElementById("saveResultsVersion");
  if (!saveButton) {
    return;
  }
  saveButton.textContent = (savedResultsVersionExists || Boolean(activeViewedVersionContext))
    ? "Update Report"
    : "Save Report";
}

function renderSavedVersionsDropdown(items) {
  const select = document.getElementById("savedVersions");
  if (!select) {
    return;
  }

  savedVersionItems = Array.isArray(items) ? items : [];
  select.innerHTML = "";

  if (savedVersionItems.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No saved versions";
    select.appendChild(option);
    updateActionButtons();
    return;
  }

  for (const item of savedVersionItems) {
    const option = document.createElement("option");
    option.value = String(item.id || "");
    option.dataset.currentScope = Boolean(item.current_scope || item.currentScope) ? "true" : "false";
    const versionTimestamp = new Date(
      item.updated_at
      || item.updatedAt
      || item.created_at
      || item.createdAt
      || Date.now()
    );
    const customName = String(item.version_name || item.versionName || "").trim();
    option.textContent = customName || `Version ${versionTimestamp.toLocaleString()}`;
    select.appendChild(option);
  }

  select.selectedIndex = 0;
  updateActionButtons();
}

function getSelectedSavedVersionItem() {
  const selectedVersionId = Number(document.getElementById("savedVersions")?.value || 0);
  if (!selectedVersionId) {
    return null;
  }
  return (savedVersionItems || []).find((item) => Number(item?.id || 0) === selectedVersionId) || null;
}

function normalizeExcelSheetNameCandidate(rawName) {
  const fallback = "Saved Report";
  const cleaned = String(rawName || "")
    .replace(/[\\/?*\[\]:]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const candidate = cleaned || fallback;
  return candidate.slice(0, MAX_EXCEL_SHEET_NAME_LENGTH);
}

async function createUniqueWorksheetName(baseName) {
  const normalizedBase = normalizeExcelSheetNameCandidate(baseName);

  return Excel.run(async (context) => {
    const worksheets = context.workbook.worksheets;
    worksheets.load("items/name");
    await context.sync();

    const existingNames = new Set((worksheets.items || []).map((sheet) => String(sheet.name || "").trim()));
    if (!existingNames.has(normalizedBase)) {
      return normalizedBase;
    }

    let suffixIndex = 2;
    while (suffixIndex < 1000) {
      const suffix = ` (${suffixIndex})`;
      const candidate = `${normalizedBase.slice(0, Math.max(1, MAX_EXCEL_SHEET_NAME_LENGTH - suffix.length))}${suffix}`;
      if (!existingNames.has(candidate)) {
        return candidate;
      }
      suffixIndex += 1;
    }

    return `${normalizedBase.slice(0, 26)} (${Date.now() % 1000})`;
  });
}

function toExcelCellValue(value) {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function deriveSavedReportHeaders(savedData, mappedHeaders) {
  const headerSet = new Set();

  if (Array.isArray(savedData)) {
    for (const row of savedData) {
      if (!row || typeof row !== "object" || Array.isArray(row)) {
        continue;
      }
      for (const key of Object.keys(row)) {
        const normalized = String(key || "").trim();
        if (normalized) {
          headerSet.add(normalized);
        }
      }
    }
  }

  if (headerSet.size === 0 && mappedHeaders && typeof mappedHeaders === "object" && !Array.isArray(mappedHeaders)) {
    for (const [key, value] of Object.entries(mappedHeaders)) {
      const mapped = String(value || "").trim();
      const source = String(key || "").trim();
      if (mapped) {
        headerSet.add(mapped);
      } else if (source) {
        headerSet.add(source);
      }
    }
  }

  return Array.from(headerSet);
}

async function launchSavedReportSheet({ versionName, savedData, mappedHeaders }) {
  const sheetName = await createUniqueWorksheetName(versionName);
  const dataRows = Array.isArray(savedData) ? savedData : [];
  const headers = deriveSavedReportHeaders(dataRows, mappedHeaders);

  appendDebugLog("Launching saved report sheet", {
    sheetName,
    rows: dataRows.length,
    columns: headers.length,
  });

  if (headers.length === 0) {
    throw new Error("Saved report has no tabular data to launch.");
  }

  await Excel.run(async (context) => {
    const worksheet = context.workbook.worksheets.add(sheetName);
    const colCount = Math.max(1, headers.length);

    const headerRowRange = worksheet.getRangeByIndexes(0, 0, 1, colCount);
    headerRowRange.values = [headers];
    await context.sync();

    const WRITE_BATCH_SIZE = 1000;
    for (let start = 0; start < dataRows.length; start += WRITE_BATCH_SIZE) {
      const batchRows = dataRows.slice(start, start + WRITE_BATCH_SIZE);
      const normalizedBatch = batchRows.map((row) => headers.map((header) => toExcelCellValue(
        row && typeof row === "object" && !Array.isArray(row) ? row[header] : ""
      )));
      const dataRange = worksheet.getRangeByIndexes(1 + start, 0, normalizedBatch.length, colCount);
      dataRange.values = normalizedBatch;
      await context.sync();
      appendDebugLog("Saved report write batch complete", {
        sheetName,
        start,
        count: normalizedBatch.length,
      });
    }

    const headerRange = worksheet.getRangeByIndexes(0, 0, 1, colCount);
    headerRange.format.font.bold = true;
    headerRange.format.fill.color = "#ffffff";
    headerRange.format.font.color = "#000000";

    const usedRange = worksheet.getUsedRangeOrNullObject();
    usedRange.load("isNullObject");
    await context.sync();
    if (!usedRange.isNullObject) {
      usedRange.format.autofitColumns();
    }
    worksheet.activate();
    await context.sync();
  });

  return sheetName;
}

async function persistPackConfigurationForSheet(testPack, packConfig, sheetName) {
  const normalizedPack = String(testPack || "").trim().toLowerCase();
  const normalizedSheetName = String(sheetName || "").trim();
  const excelUserEmail = getExcelUserEmail();
  if (!normalizedPack || !normalizedSheetName || !excelUserEmail) {
    return;
  }

  const workbookName = getWorkbookName();
  const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/pack-config`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-Excel-User-Email": excelUserEmail,
    },
    body: JSON.stringify({
      test_pack: normalizedPack,
      sheet_name: normalizedSheetName,
      workbook_name: workbookName,
      pack_config: packConfig && typeof packConfig === "object" && !Array.isArray(packConfig) ? packConfig : {},
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const detail = formatBackendErrorDetail(errorData?.detail) || `HTTP ${response.status}`;
    throw new Error(`Could not persist restored pack configuration: ${detail}`);
  }
}

async function applySavedVersionPackConfiguration(testPack, packConfig) {
  const normalizedPack = String(testPack || "").trim().toLowerCase();
  if (!normalizedPack) {
    throw new Error("Saved report does not include a test pack.");
  }

  const testPackSelect = document.getElementById("testPacks");
  const availablePackValues = Array.from(testPackSelect?.options || []).map((option) => String(option.value || "").trim().toLowerCase());
  if (!availablePackValues.includes(normalizedPack)) {
    throw new Error(`Saved report uses pack '${normalizedPack}', which is not available for this user.`);
  }

  const normalizedConfig = withDefaultEnabledTests(
    {
      [normalizedPack]: normalizePackConfigShape(
        {
          ...getDefaultPackConfig(normalizedPack),
          ...(packConfig && typeof packConfig === "object" && !Array.isArray(packConfig) ? packConfig : {}),
        },
        normalizedPack
      ),
    },
    normalizedPack
  )[normalizedPack];

  packConfigsByPack[normalizedPack] = normalizedConfig;
  if (testPackSelect) {
    testPackSelect.value = normalizedPack;
  }
  currentPackSelection = normalizedPack;
  renderSelectedPackConfig(normalizedPack);
  await syncTerritorySelectorForSelectedPack();
  return normalizedConfig;
}

async function viewSelectedSavedVersion() {
  const button = document.getElementById("viewSavedVersion");
  const selectedVersion = getSelectedSavedVersionItem();
  if (!selectedVersion) {
    setStatus("Select a saved version to view.", true);
    return;
  }

  if (Boolean(selectedVersion.current_scope || selectedVersion.currentScope)) {
    setStatus("The selected saved version is already for the active sheet.", true);
    updateActionButtons();
    return;
  }

  const excelUserEmail = getExcelUserEmail();
  if (!excelUserEmail) {
    setStatus("Could not determine Excel user email.", true);
    return;
  }

  if (button) {
    button.disabled = true;
  }

  try {
    appendDebugLog("View saved version clicked", {
      versionId: Number(selectedVersion.id),
      currentScope: Boolean(selectedVersion.current_scope || selectedVersion.currentScope),
    });
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/results/versions/${Number(selectedVersion.id)}`, {
      method: "GET",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const detail = formatBackendErrorDetail(errorData?.detail) || `HTTP ${response.status}`;
      throw new Error(detail);
    }

    const payload = await response.json().catch(() => ({}));
    appendDebugLog("Fetched saved version payload", {
      versionId: Number(selectedVersion.id),
      testPack: payload?.test_pack,
      savedDataRows: Array.isArray(payload?.saved_data) ? payload.saved_data.length : 0,
      mappedHeaderCount: payload?.mapped_headers && typeof payload.mapped_headers === "object"
        ? Object.keys(payload.mapped_headers).length
        : 0,
    });
    const versionName = String(
      payload?.version_name
      || payload?.versionName
      || selectedVersion?.version_name
      || selectedVersion?.versionName
      || "Saved Report"
    ).trim();

    setStatus("Launching saved report in a new worksheet...");
    const launchedSheetName = await launchSavedReportSheet({
      versionName,
      savedData: payload?.saved_data,
      mappedHeaders: payload?.mapped_headers,
    });

    const normalizedConfig = await applySavedVersionPackConfiguration(payload?.test_pack, payload?.pack_config);
    await persistPackConfigurationForSheet(payload?.test_pack, normalizedConfig, launchedSheetName);
    setViewedVersionContextForSheet({
      workbookName: getWorkbookName() || "__unknown_workbook__",
      sheetName: launchedSheetName,
      versionId: Number(payload?.id || selectedVersion?.id || 0),
      sheetKeyId: Number(payload?.sheet_key_id || 0),
      testPack: payload?.test_pack,
      versionName,
    });
    await refreshActiveViewedVersionContext();
    appendDebugLog("Saved version config restored and persisted", {
      versionId: Number(selectedVersion.id),
      launchedSheetName,
      testPack: payload?.test_pack,
    });
    await refreshVersionStateForActiveSheet();

    setStatus(`Saved report launched in '${launchedSheetName}'. Running validation...`);
    await runValidation();
    appendDebugLog("Validation run completed for launched saved version", {
      launchedSheetName,
      versionId: Number(selectedVersion.id),
    });
  } catch (error) {
    appendDebugLog("View saved version failed", {
      message: String(error?.message || "Unexpected error"),
      stack: String(error?.stack || ""),
    });
    setStatus(`View failed: ${error?.message || "Unexpected error"}`, true);
  } finally {
    if (button) {
      button.disabled = false;
    }
    updateActionButtons();
  }
}

function updateSavedResultsInfo() {
  const info = document.getElementById("savedResultsInfo");
  if (!info) {
    updateSaveButtonLabel();
    return;
  }

  if (!savedResultsVersionExists) {
    info.textContent = "Saved version: none";
    updateSaveButtonLabel();
    return;
  }

  const date = savedResultsVersionCreatedAt ? new Date(savedResultsVersionCreatedAt) : null;
  const label = date && !Number.isNaN(date.getTime())
    ? date.toLocaleString()
    : "available";
  info.textContent = `Saved version: ${label}`;
  updateSaveButtonLabel();
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
  const width = SANKEY_EXPORT_WIDTH;
  const height = SANKEY_EXPORT_HEIGHT;
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
    TOTAL: '#e5e7eb',
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
    DATA_TYPE: '#a78bfa', // purple
    COMPLETENESS: '#f9a8d4', // pink
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
  nodeColourMap.set('Total Tests', COLOR.TOTAL);
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
        // Keep the same aspect ratio as the exported Sankey image
        try { imgShape.width = SANKEY_DISPLAY_WIDTH; } catch {}
        try { imgShape.height = SANKEY_DISPLAY_HEIGHT; } catch {}
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
  if (territoryGroup) {
    territoryGroup.style.display = "";
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
  if (!packConfigEditor) {
    return;
  }
  const config = withDefaultEnabledTests(
    { [normalizedPack]: packConfigsByPack[normalizedPack] || getDefaultPackConfig(normalizedPack) },
    normalizedPack
  )[normalizedPack];
  config.testPack = normalizedPack;
  packConfigsByPack[normalizedPack] = config;
  packConfigEditor.value = JSON.stringify(config, null, 2);
}

function syncPackConfigEditorWithSelectedPack() {
  const testPackSelect = document.getElementById("testPacks");
  const packConfigEditor = document.getElementById("packConfigs");
  if (!testPackSelect || !packConfigEditor) {
    return;
  }

  const selectedPack = testPackSelect.value;
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
      testPackSelect.value = currentPackSelection;
      setStatus("Pack configs JSON is invalid.", true);
      return;
    }
  }

  currentPackSelection = normalizedPack;
  renderSelectedPackConfig(normalizedPack);
}

function getExcelUserEmail() {
  let officeProfileEmail = null;
  try {
    officeProfileEmail = Office?.context?.userProfile?.emailAddress || null;
  } catch {
    officeProfileEmail = null;
  }

  const email = officeProfileEmail || DEFAULT_EXCEL_EMAIL;
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

async function hydrateSelectedPackConfigFromServer(options = {}) {
  const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
  if (!selectedPack) {
    return;
  }

  const excelUserEmail = getExcelUserEmail();
  const sheetName = String(options.sheetName || await getActiveSheetName() || "").trim();
  if (!excelUserEmail || !sheetName) {
    return;
  }

  const query = new URLSearchParams({
    test_pack: selectedPack,
    sheet_name: sheetName,
  });
  const workbookName = String(options.workbookName || getWorkbookName() || "").trim();
  if (workbookName) {
    query.set("workbook_name", workbookName);
  }

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
    if (workbookName || sheetName) {
      storePackConfigStateForSheet(workbookName || "__unknown_workbook__", sheetName, {
        selectedPack,
        packConfigsByPack,
      });
    }
    if (currentPackSelection === selectedPack) {
      renderSelectedPackConfig(selectedPack);
    }
  } catch {
    // Best-effort hydration only.
  }
}

function initializeValidatorTabs() {
  const tabs = [
    {
      button: document.getElementById("tabConfiguration"),
      panel: document.getElementById("panelConfiguration"),
    },
    {
      button: document.getElementById("tabControl"),
      panel: document.getElementById("panelControl"),
    },
    {
      button: document.getElementById("tabAnalysis"),
      panel: document.getElementById("panelAnalysis"),
    },
  ];

  if (tabs.some((tab) => !tab.button || !tab.panel)) {
    return;
  }

  const activateTab = (targetButtonId) => {
    for (const { button, panel } of tabs) {
      const isActive = button.id === targetButtonId;
      button.setAttribute("aria-selected", isActive ? "true" : "false");
      button.tabIndex = isActive ? 0 : -1;
      panel.classList.toggle("active", isActive);
    }
  };

  for (const { button } of tabs) {
    button.addEventListener("click", () => activateTab(button.id));
  }

  activateTab("tabConfiguration");
}


// ============================================================================
// EXCEPTION MANAGEMENT FUNCTIONS
// ============================================================================

async function loadExceptions() {
  try {
    const excelUserEmail = getExcelUserEmail();
    if (!excelUserEmail) {
      return;
    }

    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/exceptions`, {
      method: "GET",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return;
    }

    const payload = await response.json().catch(() => ({ exceptions: [] }));
    const exceptions = Array.isArray(payload?.exceptions) ? payload.exceptions : [];
    
    // Populate exception dropdown in control panel
    const exceptionSelect = document.getElementById("exceptionSelect");
    if (exceptionSelect) {
      exceptionSelect.innerHTML = "";
      if (exceptions.length === 0) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No exceptions available";
        exceptionSelect.appendChild(option);
      } else {
        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = "Select an exception...";
        exceptionSelect.appendChild(defaultOption);
        
        for (const exc of exceptions) {
          const option = document.createElement("option");
          option.value = exc.exception_id;
          option.textContent = exc.exception_id;
          option.dataset.exceptionData = JSON.stringify(exc);
          exceptionSelect.appendChild(option);
        }
      }
    }
  } catch {
    // Silently fail
  }
}

function normalizeExceptionMatchValue(value) {
  return String(value || "").trim().toLowerCase();
}

function buildLinkedExceptionLookup(exceptions) {
  const lookup = new Map();

  for (const rawException of exceptions || []) {
    const exceptionId = String(rawException?.exception_id || "").trim();
    const linkedField = String(rawException?.linked_field || rawException?.test_id || "").trim();
    const linkedUmr = String(rawException?.linked_umr || "").trim();

    if (!exceptionId || !linkedField || !linkedUmr) {
      continue;
    }

    const key = `${normalizeExceptionMatchValue(linkedUmr)}::${normalizeExceptionMatchValue(linkedField)}`;
    if (!lookup.has(key)) {
      lookup.set(key, {
        exception_id: exceptionId,
        linked_field: linkedField,
        linked_umr: linkedUmr,
      });
    }
  }

  return lookup;
}

async function fetchStoredExceptionsForAutoTagging(excelUserEmail) {
  if (!excelUserEmail) {
    return [];
  }

  try {
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/exceptions`, {
      method: "GET",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return [];
    }

    const payload = await response.json().catch(() => ({ exceptions: [] }));
    return Array.isArray(payload?.exceptions) ? payload.exceptions : [];
  } catch {
    return [];
  }
}

async function loadLinkedFieldsForExceptionModal() {
  try {
    const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
    const query = selectedPack ? `?test_pack=${encodeURIComponent(selectedPack)}` : "";

    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/rules-engine${query}`, {
      method: "GET",
      cache: "no-store",
    });

    if (!response.ok) {
      return;
    }

    const payload = await response.json().catch(() => ({ rules: [] }));
    const rules = Array.isArray(payload?.rules) ? payload.rules : [];
    const fields = Array.from(new Set(rules.map((r) => String(r?.target_column || "").trim()).filter(Boolean)));
    
    const fieldSelect = document.getElementById("exceptionFieldInput");
    if (fieldSelect) {
      const currentValue = fieldSelect.value;
      fieldSelect.innerHTML = "";
      
      const defaultOption = document.createElement("option");
      defaultOption.value = "";
      defaultOption.textContent = "Select a field...";
      fieldSelect.appendChild(defaultOption);
      
      for (const fieldName of fields.sort((a, b) => a.localeCompare(b))) {
        const option = document.createElement("option");
        option.value = fieldName;
        option.textContent = fieldName;
        fieldSelect.appendChild(option);
      }
      
      fieldSelect.value = currentValue;
    }
  } catch {
    // Silently fail
  }
}

function openExceptionModal() {
  const modal = document.getElementById("exceptionModal");
  if (modal) {
    modal.classList.add("active");
    loadLinkedFieldsForExceptionModal();
    renderExceptionList();
  }
}

function closeExceptionModal() {
  const modal = document.getElementById("exceptionModal");
  if (modal) {
    modal.classList.remove("active");
  }
  // Clear form
  document.getElementById("exceptionIdInput").value = "";
  document.getElementById("exceptionFieldInput").value = "";
  document.getElementById("exceptionUmrInput").value = "";
  document.getElementById("exceptionDescriptionInput").value = "";
  document.getElementById("exceptionStatusInput").value = "to do";
  
  // Reset form title and button
  const formTitle = document.getElementById("exceptionFormTitle");
  if (formTitle) {
    formTitle.textContent = "Create New Exception";
  }
  const createBtn = document.getElementById("createExceptionBtn");
  if (createBtn) {
    createBtn.textContent = "Create";
    createBtn.dataset.editMode = "false";
    delete createBtn.dataset.originalExceptionId;
  }
}

async function renderExceptionList() {
  try {
    const excelUserEmail = getExcelUserEmail();
    if (!excelUserEmail) {
      return;
    }

    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/exceptions`, {
      method: "GET",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return;
    }

    const payload = await response.json().catch(() => ({ exceptions: [] }));
    const exceptions = Array.isArray(payload?.exceptions) ? payload.exceptions : [];
    
    const container = document.getElementById("exceptionListContainer");
    const list = document.getElementById("exceptionList");
    const noMessage = document.getElementById("noExceptionsMessage");
    
    if (exceptions.length === 0) {
      if (container) container.style.display = "none";
      if (noMessage) noMessage.style.display = "block";
      return;
    }
    
    if (container) container.style.display = "block";
    if (noMessage) noMessage.style.display = "none";
    
    list.innerHTML = "";
    for (const exc of exceptions) {
      const item = document.createElement("div");
      item.className = "exception-item";

      const info = document.createElement("div");
      info.className = "exception-info";

      const idNode = document.createElement("div");
      idNode.className = "exception-id";
      idNode.textContent = exc.exception_id || "";

      const status = document.createElement("span");
      status.className = "exception-status";
      status.textContent = (exc.status || "").replace(/\b\w/g, c => c.toUpperCase());

      const descNode = document.createElement("div");
      descNode.className = "exception-desc";
      const fullDescription = String(exc.description || "");
      descNode.title = fullDescription;
      const firstDescriptionLine = fullDescription.split(/\r?\n/, 1)[0].trim();
      descNode.textContent = truncateText(firstDescriptionLine, 16);

      info.appendChild(idNode);
      info.appendChild(status);
      info.appendChild(descNode);

      const linkedField = String(exc.linked_field || exc.test_id || "").trim();
      if (linkedField) {
        const fieldNode = document.createElement("div");
        fieldNode.style.fontSize = "11px";
        fieldNode.style.color = "#666";
        fieldNode.textContent = `Field: ${linkedField}`;
        info.appendChild(fieldNode);
      }

      const linkedUmr = String(exc.linked_umr || "").trim();
      if (linkedUmr) {
        const umrNode = document.createElement("div");
        umrNode.style.fontSize = "11px";
        umrNode.style.color = "#666";
        umrNode.textContent = `UMR: ${linkedUmr}`;
        info.appendChild(umrNode);
      }

      const actions = document.createElement("div");
      actions.className = "exception-actions";

      const editBtn = document.createElement("button");
      editBtn.className = "icon-btn";
      editBtn.type = "button";
      editBtn.textContent = "Edit";
      editBtn.addEventListener("click", () => {
        editException(exc.exception_id);
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.className = "icon-btn";
      deleteBtn.type = "button";
      deleteBtn.style.color = "#dc2626";
      deleteBtn.textContent = "Delete";
      deleteBtn.addEventListener("click", () => {
        deleteException(exc.exception_id);
      });

      actions.appendChild(editBtn);
      actions.appendChild(deleteBtn);

      item.appendChild(info);
      item.appendChild(actions);
      list.appendChild(item);
    }
  } catch {
    // Silently fail
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function truncateText(text, maxLength = 16) {
  if (!text) return "";
  return text.length > maxLength ? text.substring(0, maxLength) + "..." : text;
}

function promptForReportName(defaultValue = "") {
  return new Promise((resolve) => {
    const existing = document.getElementById("reportNamePromptOverlay");
    if (existing) {
      existing.remove();
    }

    const overlay = document.createElement("div");
    overlay.id = "reportNamePromptOverlay";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.background = "rgba(0, 0, 0, 0.35)";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.zIndex = "99999";

    const panel = document.createElement("div");
    panel.style.background = "#ffffff";
    panel.style.borderRadius = "10px";
    panel.style.boxShadow = "0 10px 28px rgba(0, 0, 0, 0.22)";
    panel.style.width = "min(380px, calc(100vw - 60px))";
    panel.style.maxWidth = "380px";
    panel.style.padding = "16px";
    panel.style.fontFamily = "Segoe UI, sans-serif";

    const title = document.createElement("div");
    title.textContent = "Save report";
    title.style.fontWeight = "600";
    title.style.fontSize = "14px";
    title.style.marginBottom = "10px";

    const label = document.createElement("label");
    label.textContent = "Report name";
    label.style.display = "block";
    label.style.fontSize = "12px";
    label.style.marginBottom = "6px";

    const input = document.createElement("input");
    input.type = "text";
    input.value = String(defaultValue || "").trim().slice(0, 32);
    input.placeholder = "Enter report name";
    input.maxLength = 32;
    input.style.width = "100%";
    input.style.boxSizing = "border-box";
    input.style.padding = "8px 10px";
    input.style.border = "1px solid #cbd5e1";
    input.style.borderRadius = "6px";
    input.style.marginBottom = "4px";

    const charHint = document.createElement("div");
    charHint.style.fontSize = "11px";
    charHint.style.color = "#94a3b8";
    charHint.style.textAlign = "right";
    charHint.style.marginBottom = "10px";
    charHint.textContent = `${input.value.length}/32`;
    input.addEventListener("input", () => {
      charHint.textContent = `${input.value.length}/32`;
    });

    const actions = document.createElement("div");
    actions.style.display = "flex";
    actions.style.justifyContent = "flex-end";
    actions.style.gap = "8px";

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.textContent = "Cancel";
    cancelButton.className = "btn-secondary";

    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.textContent = "Save";

    const finish = (value) => {
      overlay.remove();
      resolve(value);
    };

    cancelButton.addEventListener("click", () => finish(null));
    saveButton.addEventListener("click", () => {
      const value = String(input.value || "").trim();
      if (!value) {
        input.focus();
        return;
      }
      finish(value);
    });

    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) {
        finish(null);
      }
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        saveButton.click();
      }
      if (event.key === "Escape") {
        event.preventDefault();
        finish(null);
      }
    });

    actions.appendChild(cancelButton);
    actions.appendChild(saveButton);
    panel.appendChild(title);
    panel.appendChild(label);
    panel.appendChild(input);
    panel.appendChild(charHint);
    panel.appendChild(actions);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => {
      input.focus();
      input.select();
    });
  });
}

function splitTaggedCellsByException(exceptionId) {
  const normalizedExceptionId = String(exceptionId || "").trim();
  const removed = [];
  const kept = [];

  for (const rawItem of lastTaggedCells || []) {
    const taggedCell = normalizeTaggedCellRecord(rawItem);
    if (!taggedCell) {
      continue;
    }
    if (taggedCell.exception_id === normalizedExceptionId) {
      removed.push(taggedCell);
    } else {
      kept.push(taggedCell);
    }
  }

  return { removed, kept };
}

async function unapplyDeletedExceptionFromWorkbook(exceptionId, removedTaggedCells, remainingTaggedCells) {
  const normalizedExceptionId = String(exceptionId || "").trim();
  const activeWorkbookName = String(getWorkbookName() || "").trim();

  const removedInActiveWorkbook = (removedTaggedCells || [])
    .map((item) => normalizeTaggedCellRecord(item))
    .filter((item) => {
      if (!item) {
        return false;
      }
      if (!activeWorkbookName) {
        return true;
      }
      const taggedWorkbook = String(item.workbook_name || "").trim();
      return (
        !taggedWorkbook
        || taggedWorkbook === activeWorkbookName
        || taggedWorkbook === "__unknown_workbook__"
      );
    });

  if (!removedInActiveWorkbook.length) {
    return;
  }

  const remainingByCell = new Set();
  for (const rawItem of remainingTaggedCells || []) {
    const taggedCell = normalizeTaggedCellRecord(rawItem);
    if (!taggedCell) {
      continue;
    }
    remainingByCell.add(`${taggedCell.sheet_name}::${taggedCell.address}`);
  }

  await Excel.run(async (context) => {
    const workbook = context.workbook;
    const worksheets = workbook.worksheets;
    worksheets.load("items/name");
    await context.sync();

    const worksheetByName = new Map();
    for (const sheet of worksheets.items) {
      worksheetByName.set(String(sheet.name || "").trim(), sheet);
    }

    const removedBySheet = new Map();
    for (const taggedCell of removedInActiveWorkbook) {
      const sheetName = String(taggedCell.sheet_name || "").trim();
      if (!sheetName) {
        continue;
      }
      if (!removedBySheet.has(sheetName)) {
        removedBySheet.set(sheetName, []);
      }
      removedBySheet.get(sheetName).push(taggedCell);
    }

    const sheetCommentsMap = new Map();
    const commentProxies = [];
    for (const [sheetName] of removedBySheet) {
      const worksheet = worksheetByName.get(sheetName);
      if (!worksheet) {
        continue;
      }
      const comments = worksheet.comments;
      comments.load("items");
      sheetCommentsMap.set(sheetName, comments);
    }
    await context.sync();

    const sheetCommentLookup = new Map();
    for (const [sheetName, comments] of sheetCommentsMap.entries()) {
      const entries = [];
      for (const comment of comments.items) {
        comment.load("content");
        const location = comment.getLocation();
        location.load("address");
        entries.push({ comment, location });
      }
      commentProxies.push({ sheetName, entries });
    }
    await context.sync();

    for (const { sheetName, entries } of commentProxies) {
      const lookup = new Map();
      for (const { comment, location } of entries) {
        const address = String(location.address || "");
        const cellPart = address.includes("!") ? address.split("!")[1] : address;
        lookup.set(String(cellPart || "").trim().toUpperCase(), comment);
      }
      sheetCommentLookup.set(sheetName, lookup);
    }

    for (const [sheetName, taggedCells] of removedBySheet.entries()) {
      const worksheet = worksheetByName.get(sheetName);
      if (!worksheet) {
        continue;
      }
      const commentLookup = sheetCommentLookup.get(sheetName) || new Map();

      for (const taggedCell of taggedCells) {
        const cellKey = `${sheetName}::${taggedCell.address}`;
        const hasRemainingTag = remainingByCell.has(cellKey);
        const range = worksheet.getRange(taggedCell.address);

        if (!hasRemainingTag) {
          const previousFill = String(taggedCell.previous_fill_color || "").trim();
          if (previousFill) {
            range.format.fill.color = previousFill;
          } else {
            range.format.fill.clear();
          }
        }

        const comment = commentLookup.get(taggedCell.address);
        if (!comment) {
          continue;
        }

        const originalLines = String(comment.content || "")
          .split(/\r?\n/)
          .map((line) => String(line || "").trim())
          .filter((line) => line.length > 0);

        const filteredLines = originalLines.filter(
          (line) => line !== `Exception tagged: ${normalizedExceptionId}`
        );

        if (filteredLines.length === originalLines.length) {
          continue;
        }

        if (filteredLines.length === 0) {
          comment.delete();
        } else {
          comment.content = filteredLines.join("\n");
        }
      }
    }

    await context.sync();
  });
}

async function getCurrentFillColorsForAddresses(addresses) {
  const addressList = Array.isArray(addresses)
    ? addresses
      .map((address) => String(address || "").replace(/\$/g, "").trim().toUpperCase())
      .filter(Boolean)
    : [];

  if (!addressList.length) {
    return new Map();
  }

  return Excel.run(async (context) => {
    const worksheet = context.workbook.worksheets.getActiveWorksheet();
    const entries = [];

    for (const address of addressList) {
      const range = worksheet.getRange(address);
      range.format.fill.load("color");
      entries.push({ address, range });
    }

    await context.sync();

    const fillByAddress = new Map();
    for (const { address, range } of entries) {
      fillByAddress.set(address, String(range.format.fill.color || "").trim());
    }
    return fillByAddress;
  });
}


async function createException() {
  const exceptionId = document.getElementById("exceptionIdInput").value.trim();
  const linkedField = document.getElementById("exceptionFieldInput").value.trim() || null;
  const linkedUmr = document.getElementById("exceptionUmrInput").value.trim() || null;
  const description = document.getElementById("exceptionDescriptionInput").value.trim();
  const status = document.getElementById("exceptionStatusInput").value;
  
  if (!exceptionId || !description) {
    setStatus("Exception ID and Description are required.", true);
    return;
  }

  const excelUserEmail = getExcelUserEmail();
  if (!excelUserEmail) {
    setStatus("Could not determine Excel user email.", true);
    return;
  }

  const createBtn = document.getElementById("createExceptionBtn");
  const isEditMode = createBtn.dataset.editMode === "true";
  const originalExceptionId = createBtn.dataset.originalExceptionId;

  try {
    if (isEditMode) {
      // Update existing exception
      const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/exceptions/${encodeURIComponent(originalExceptionId)}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-Excel-User-Email": excelUserEmail,
        },
        body: JSON.stringify({
          exception_id: exceptionId,
          linked_field: linkedField,
          linked_umr: linkedUmr,
          description: description,
          status: status,
        }),
      });

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        const errorMsg = errorPayload?.detail || "Failed to update exception";
        setStatus(`Error: ${errorMsg}`, true);
        return;
      }

      setStatus("Exception updated successfully.");
    } else {
      // Create new exception
      const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/exceptions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Excel-User-Email": excelUserEmail,
        },
        body: JSON.stringify({
          exception_id: exceptionId,
          linked_field: linkedField,
          linked_umr: linkedUmr,
          description: description,
          status: status,
        }),
      });

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        const errorMsg = errorPayload?.detail || "Failed to create exception";
        setStatus(`Error: ${errorMsg}`, true);
        return;
      }

      setStatus("Exception created successfully.");
    }
    
    // Clear form and refresh list
    document.getElementById("exceptionIdInput").value = "";
    document.getElementById("exceptionFieldInput").value = "";
    document.getElementById("exceptionUmrInput").value = "";
    document.getElementById("exceptionDescriptionInput").value = "";
    document.getElementById("exceptionStatusInput").value = "to do";
    
    // Reset button state
    createBtn.textContent = "Create";
    createBtn.dataset.editMode = "false";
    createBtn.dataset.originalExceptionId = "";
    
    await renderExceptionList();
    await loadExceptions();
  } catch (error) {
    setStatus(`Error: ${error?.message || "Unknown error"}`, true);
  }
}

async function deleteException(exceptionId) {
  if (!String(exceptionId || "").trim()) {
    setStatus("Missing exception ID.", true);
    return;
  }

  const excelUserEmail = getExcelUserEmail();
  if (!excelUserEmail) {
    setStatus("Could not determine Excel user email.", true);
    return;
  }

  const { removed: locallyRemovedTags, kept: locallyKeptTags } = splitTaggedCellsByException(exceptionId);
  setStatus(`Deleting exception '${exceptionId}'...`);

  try {
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/exceptions/${encodeURIComponent(exceptionId)}`, {
      method: "DELETE",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const detail = formatBackendErrorDetail(errorData?.detail) || `HTTP ${response.status}`;
      setStatus(`Failed to delete exception: ${detail}`, true);
      return;
    }

    const payload = await response.json().catch(() => ({}));
    const removedFromBackend = Array.isArray(payload?.removed_tagged_cells)
      ? payload.removed_tagged_cells
      : [];
    const tagsToRemoveFromSheet = removedFromBackend.length ? removedFromBackend : locallyRemovedTags;

    lastTaggedCells = locallyKeptTags;
    persistValidationResults();

    try {
      await unapplyDeletedExceptionFromWorkbook(exceptionId, tagsToRemoveFromSheet, lastTaggedCells);
    } catch {
      // Best effort only: metadata is still cleaned and exception has been deleted.
    }

    setStatus("Exception deleted successfully.");
    await renderExceptionList();
    await loadExceptions();
  } catch (error) {
    setStatus(`Error: ${error?.message || "Unknown error"}`, true);
  }
}

async function editException(exceptionId) {
  const excelUserEmail = getExcelUserEmail();
  if (!excelUserEmail) {
    setStatus("Could not determine Excel user email.", true);
    return;
  }

  try {
    // Fetch the current exception data
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/exceptions`, {
      method: "GET",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      setStatus("Failed to load exception details.", true);
      return;
    }

    const payload = await response.json().catch(() => ({ exceptions: [] }));
    const exceptions = Array.isArray(payload?.exceptions) ? payload.exceptions : [];
    const exception = exceptions.find(e => e.exception_id === exceptionId);

    if (!exception) {
      setStatus("Exception not found.", true);
      return;
    }

    // Populate the form with existing data
    document.getElementById("exceptionIdInput").value = exception.exception_id;
    await loadLinkedFieldsForExceptionModal();
    document.getElementById("exceptionFieldInput").value = exception.linked_field || exception.test_id || "";
    document.getElementById("exceptionUmrInput").value = exception.linked_umr || "";
    document.getElementById("exceptionDescriptionInput").value = exception.description;
    document.getElementById("exceptionStatusInput").value = exception.status;

    // Change button text to indicate update mode
    const createBtn = document.getElementById("createExceptionBtn");
    const originalText = createBtn.textContent;
    createBtn.textContent = "Update";
    createBtn.dataset.editMode = "true";
    createBtn.dataset.originalExceptionId = exceptionId;

    // Change heading to indicate edit mode
    const formTitle = document.getElementById("exceptionFormTitle");
    if (formTitle) {
      formTitle.textContent = "Edit Exception";
    }

    // Scroll to form
    document.querySelector('input[id="exceptionIdInput"]').focus();
  } catch (error) {
    setStatus(`Error: ${error?.message || "Unknown error"}`, true);
  }
}

async function applyExceptionToCell() {
  const exceptionSelect = document.getElementById("exceptionSelect");
  const selectedExceptionId = exceptionSelect?.value?.trim();
  
  if (!selectedExceptionId) {
    setStatus("Please select an exception to apply.", true);
    return;
  }

  try {
    const selection = await Excel.run(async (context) => {
      const range = context.workbook.getSelectedRange();
      const worksheet = context.workbook.worksheets.getActiveWorksheet();
      range.load("address");
      worksheet.load("name");
      await context.sync();
      return {
        address: range.address,
        sheetName: worksheet.name,
      };
    });

    if (!selection?.address) {
      setStatus("Please select at least one cell to apply exception.", true);
      return;
    }

    const workbookName = getWorkbookName() || "__unknown_workbook__";
    const sheetName = String(selection.sheetName || "").trim() || await getActiveSheetName() || "__unknown_sheet__";

    // Parse the address (e.g., "Sheet1!A1:B2") to get individual addresses
    const addresses = parseExcelAddress(selection.address);
    if (addresses.length === 0) {
      setStatus("Could not parse selected cell address.", true);
      return;
    }

    const previousFillByAddress = await getCurrentFillColorsForAddresses(addresses);

    const taggedCells = addresses.map((address) => ({
      address,
      exception_id: selectedExceptionId,
      comment: `Exception tagged: ${selectedExceptionId}`,
      fill_color: EXCEPTION_TAG_FILL,
      previous_fill_color: String(previousFillByAddress.get(address) || "").trim(),
      sheet_name: sheetName,
      workbook_name: workbookName,
      tagged_at: new Date().toISOString(),
    }));

    setStatus("Applying exception to selected cells...");
    await applyExceptionTagsToSheet(taggedCells);
    lastTaggedCells = mergeTaggedCells(lastTaggedCells, taggedCells);
    persistValidationResults();
    await syncTaggedCellsToBackend(selectedExceptionId, addresses, sheetName, workbookName, taggedCells);
    setStatus(`Exception '${selectedExceptionId}' applied to ${addresses.length} cell(s).`);
  } catch (error) {
    setStatus(`Error: ${error?.message || "Unknown error"}`, true);
  }
}

function parseExcelAddress(address) {
  // Parse Excel address format like "Sheet1!A1:B2" or "Sheet1!A1"
  if (!address) return [];
  
  const parts = address.split("!");
  if (parts.length < 2) return [];
  
  const rangePart = parts[1];
  const colonIndex = rangePart.indexOf(":");
  
  let addresses = [];
  
  if (colonIndex === -1) {
    // Single cell
    addresses.push(rangePart);
  } else {
    // Range - expand to all cells
    const [startCell, endCell] = rangePart.split(":");
    const start = parseCell(startCell);
    const end = parseCell(endCell);
    
    if (start && end) {
      for (let row = start.row; row <= end.row; row++) {
        for (let col = start.col; col <= end.col; col++) {
          addresses.push(`${numberToExcelCol(col)}${row}`);
        }
      }
    }
  }
  
  return addresses;
}

function parseCell(cellStr) {
  const normalized = String(cellStr || "").replace(/\$/g, "").trim().toUpperCase();
  const match = normalized.match(/^([A-Z]+)(\d+)$/);
  if (!match) return null;
  
  const col = excelColToNumber(match[1]);
  const row = parseInt(match[2], 10);
  
  return { col, row };
}

function excelColToNumber(col) {
  let num = 0;
  for (let i = 0; i < col.length; i++) {
    num = num * 26 + (col.charCodeAt(i) - 64);
  }
  return num;
}

function numberToExcelCol(num) {
  let col = "";
  while (num > 0) {
    num--;
    col = String.fromCharCode((num % 26) + 65) + col;
    num = Math.floor(num / 26);
  }
  return col;
}

async function addExceptionComment(addresses, exceptionId) {
  const taggedCells = addresses.map((address) => ({
    address,
    exception_id: exceptionId,
    comment: `Exception tagged: ${exceptionId}`,
    fill_color: EXCEPTION_TAG_FILL,
    sheet_name: lastValidationSourceSheetName || "",
    workbook_name: getWorkbookName() || "",
    tagged_at: new Date().toISOString(),
  }));
  await applyExceptionTagsToSheet(taggedCells);
}

async function applyExceptionTagsToSheet(taggedCells) {
  await Excel.run(async (context) => {
    const worksheet = context.workbook.worksheets.getActiveWorksheet();

    const comments = worksheet.comments;
    comments.load("items");
    await context.sync();

    const commentLocations = [];
    for (const comment of comments.items) {
      comment.load("content");
      const location = comment.getLocation();
      location.load("address");
      commentLocations.push({ comment, location });
    }
    await context.sync();

    const existingCommentMap = new Map();
    for (const { comment, location } of commentLocations) {
      const addr = location.address;
      const cellPart = addr.includes("!") ? addr.split("!")[1] : addr;
      existingCommentMap.set(String(cellPart || "").trim().toUpperCase(), comment);
    }

    for (const rawItem of taggedCells || []) {
      const taggedCell = normalizeTaggedCellRecord(rawItem);
      if (!taggedCell) {
        continue;
      }
      const range = worksheet.getRange(taggedCell.address);
      range.format.fill.color = taggedCell.fill_color || EXCEPTION_TAG_FILL;

      const existingComment = existingCommentMap.get(taggedCell.address);
      const tagLine = taggedCell.comment;
      if (existingComment) {
        const existingContent = String(existingComment.content || "").trim();
        existingComment.content = existingContent.includes(tagLine)
          ? existingContent
          : (existingContent ? `${existingContent}\n${tagLine}` : tagLine);
      } else {
        worksheet.comments.add(taggedCell.address, tagLine, Excel.ContentType.plain);
      }
    }

    await context.sync();
  });
}

async function syncTaggedCellsToBackend(exceptionId, addresses, sheetName, workbookName, taggedCells = []) {
  const excelUserEmail = getExcelUserEmail();
  if (!excelUserEmail) {
    return;
  }

  const selectedPack = String(document.getElementById("testPacks")?.value || lastValidationPack || "").trim().toLowerCase();
  const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/exceptions/apply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Excel-User-Email": excelUserEmail,
    },
    body: JSON.stringify({
      exception_id: exceptionId,
      addresses,
      tagged_cells: Array.isArray(taggedCells) ? taggedCells : [],
      sheet_name: sheetName,
      workbook_name: workbookName,
      test_pack: selectedPack || null,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const detail = formatBackendErrorDetail(errorData?.detail) || `HTTP ${response.status}`;
    throw new Error(detail);
  }
}

async function reapplyTaggedCellsForScope(workbookName, sheetName) {
  const scopedTags = getTaggedCellsForScope(workbookName, sheetName);
  if (!scopedTags.length) {
    return;
  }
  await applyExceptionTagsToSheet(scopedTags);
}


async function initializeTaskpaneApp() {
  initializeValidatorTabs();

  const testPackSelect = document.getElementById("testPacks");
  if (!testPackSelect) {
    throw new Error("Could not find the test pack selector.");
  }

  const excelUserEmail = getExcelUserEmail();
  const availablePacks = populatePackSelect(await loadSubscribedPackValues(excelUserEmail));
  availablePackOptions = availablePacks.length > 0 ? availablePacks : ["risk_and_premium"];

  const defaultPackFromConfig = String(CONFIG.DEFAULT_PACK || "").trim().toLowerCase();
  const fallbackPack = availablePackOptions[0] || "risk_and_premium";
  const initialPack = availablePackOptions.includes(defaultPackFromConfig)
    ? defaultPackFromConfig
    : fallbackPack;

  testPackSelect.value = initialPack;
  if (!testPackSelect.value) {
    testPackSelect.value = fallbackPack;
  }

  packConfigsByPack = buildDefaultPackConfigs(availablePackOptions);
  currentPackSelection = getSafePackSelection(testPackSelect.value);
  renderSelectedPackConfig(currentPackSelection);

  document.getElementById("testPacks")?.addEventListener("change", async () => {
    syncPackConfigEditorWithSelectedPack();
    await hydrateSelectedPackConfigFromServer({
      workbookName: currentSheetPackConfigScope?.workbookName,
      sheetName: currentSheetPackConfigScope?.sheetName,
    });
    await syncTerritorySelectorForSelectedPack();
    await persistPackConfigStateForScope({ persistToServer: true, showValidationError: true });
    await refreshVersionStateForActiveSheet();
    if (document.getElementById("exceptionModal")?.classList.contains("active")) {
      await loadLinkedFieldsForExceptionModal();
    }
  });

  document.getElementById("territory")?.addEventListener("change", () => {
    const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
    const territory = getSelectedTerritoryValue();
    applyTerritoryToPackConfig(selectedPack, territory);
    if (currentPackSelection === selectedPack) {
      renderSelectedPackConfig(selectedPack);
    }
    schedulePackConfigStatePersist({ delayMs: 0, persistToServer: true, showValidationError: true, showSaveError: true });
  });

  document.getElementById("packConfigs")?.addEventListener("input", () => {
    schedulePackConfigStatePersist({ delayMs: 400, persistToServer: false, showValidationError: false, showSaveError: false });
  });
  document.getElementById("packConfigs")?.addEventListener("blur", () => {
    schedulePackConfigStatePersist({ delayMs: 0, persistToServer: true, showValidationError: true, showSaveError: true });
  });

  document.getElementById("runValidation")?.addEventListener("click", runValidation);
  document.getElementById("clearTable")?.addEventListener("click", clearTableFormattingAndComments);
  document.getElementById("extractResults")?.addEventListener("click", extractValidationResults);
  document.getElementById("visualiseResults")?.addEventListener("click", visualiseValidationResults);
  document.getElementById("rulesEngine")?.addEventListener("click", openRulesEngine);
  document.getElementById("saveResultsVersion")?.addEventListener("click", saveResultsVersion);
  document.getElementById("deleteResultsVersion")?.addEventListener("click", deleteSelectedResultsVersion);
  document.getElementById("viewSavedVersion")?.addEventListener("click", viewSelectedSavedVersion);
  document.getElementById("savedVersions")?.addEventListener("change", updateActionButtons);
  document.getElementById("generateTemplate")?.addEventListener("click", generateTemplate);
  document.getElementById("estimateFieldMapping")?.addEventListener("click", estimateFieldMapping);

  document.getElementById("applyException")?.addEventListener("click", applyExceptionToCell);
  document.getElementById("manageExceptions")?.addEventListener("click", openExceptionModal);
  document.getElementById("createExceptionBtn")?.addEventListener("click", createException);
  document.getElementById("closeExceptionModalBtn")?.addEventListener("click", closeExceptionModal);

  document.getElementById("exceptionModal")?.addEventListener("click", (event) => {
    const modal = document.getElementById("exceptionModal");
    if (event.target === modal) {
      closeExceptionModal();
    }
  });

  restoreValidationResults();

  try {
    await Excel.run(async (context) => {
      context.workbook.worksheets.onActivated.add(() => {
        syncPackConfigStateWithActiveSheet().catch((error) => {
          reportFrontendError("Could not refresh sheet-specific configuration", error);
        });
        
        // Ensure taskpane is visible when switching sheets
        try {
          if (typeof Office?.addin?.show === "function") {
            Office.addin.show();
          }
        } catch {
          // Best effort only
        }
        
        // Ensure Configuration tab is active
        const configTab = document.getElementById("tabConfiguration");
        if (configTab) {
          configTab.click();
        }
      });
      await context.sync();
    });
  } catch {
    // Best effort only.
  }

  await syncPackConfigStateWithActiveSheet({ skipSavePreviousSheet: true });
  await loadExceptions();
}

Office.onReady(() => {
  installGlobalFrontendErrorHandlers();
  initializeTaskpaneApp().catch((error) => {
    reportFrontendError("Taskpane initialization failed", error);
  });
});

function setStatus(message, isError = false) {
  const status = ensureStatusElement();
  if (!status) {
    return;
  }
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
  return null;
}

function extractTestIdFromFailureMessage(testMessage) {
  if (typeof testMessage === "string") {
    const raw = String(testMessage || "").trim();
    const match = raw.match(/^\[(.*?)\]\s+([A-Za-z0-9_]+):\s*(.*)$/);
    return match ? String(match[2] || "").trim() : "";
  }

  if (typeof testMessage === "object" && testMessage !== null) {
    return String(testMessage.testId || "").trim();
  }

  return "";
}

async function getCurrentResultsScope(options = {}) {
  const preferValidationSheet = Boolean(options?.preferValidationSheet);
  const workbookName = getWorkbookName() || "__unknown_workbook__";
  const activeSheetName = await getActiveSheetName();
  const selectedSheetName = preferValidationSheet
    ? (lastValidationSourceSheetName || activeSheetName)
    : activeSheetName;
  const sheetName = String(selectedSheetName || "__unknown_sheet__").trim();
  return {
    workbookName,
    sheetName: sheetName || "__unknown_sheet__",
  };
}

async function refreshVersionStateForActiveSheet() {
  await refreshActiveViewedVersionContext();
  await checkSavedResultsVersion();
  updateSaveButtonLabel();
  updateActionButtons();
}

async function checkSavedResultsVersion() {
  const excelUserEmail = getExcelUserEmail();
  if (!excelUserEmail) {
    savedResultsVersionExists = false;
    savedResultsVersionCreatedAt = null;
    renderSavedVersionsDropdown([]);
    updateSavedResultsInfo();
    updateActionButtons();
    return;
  }

  const { workbookName, sheetName } = await getCurrentResultsScope();
  const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
  if (!selectedPack) {
    savedResultsVersionExists = false;
    savedResultsVersionCreatedAt = null;
    renderSavedVersionsDropdown([]);
    updateSavedResultsInfo();
    updateActionButtons();
    return;
  }

  const query = new URLSearchParams({
    workbook_name: workbookName,
    sheet_name: sheetName,
    test_pack: selectedPack,
  });

  try {
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/results/versions?${query.toString()}`, {
      method: "GET",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      savedResultsVersionExists = false;
      savedResultsVersionCreatedAt = null;
      renderSavedVersionsDropdown([]);
      updateSavedResultsInfo();
      updateActionButtons();
      return;
    }

    const payload = await response.json().catch(() => ({}));
    const versions = Array.isArray(payload?.versions) ? payload.versions : [];
    renderSavedVersionsDropdown(versions);
    const currentScopeVersion = versions.find((item) => Boolean(item?.current_scope || item?.currentScope));
    savedResultsVersionExists = Boolean(currentScopeVersion);
    savedResultsVersionCreatedAt = savedResultsVersionExists
      ? String(currentScopeVersion?.updated_at || currentScopeVersion?.updatedAt || currentScopeVersion?.created_at || currentScopeVersion?.createdAt || "").trim() || null
      : null;
    updateSavedResultsInfo();
    updateActionButtons();
  } catch {
    savedResultsVersionExists = false;
    savedResultsVersionCreatedAt = null;
    renderSavedVersionsDropdown([]);
    updateSavedResultsInfo();
    updateActionButtons();
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

    // Clear persisted results when clearing the table
    lastValidationResults = [];
    lastValidationSourceSheetName = null;
    lastValidationExecutedTests = [];
    lastValidationPack = null;
    lastValidationFailedTests = [];
    lastValidationPassedTests = [];
    lastValidationPassedUmrs = [];
    lastTaggedCells = [];
    clearPersistedValidationResults();
    updateActionButtons();

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

async function buildCurrentSheetDataPayload() {
  const tableMeta = await resolveValidationRangeMeta();
  const dataRowCount = Math.max(0, Number(tableMeta.rowCount || 0) - 1);
  if (dataRowCount === 0) {
    return [];
  }

  const rows = await readRangeValues(
    tableMeta.startRow + 1,
    tableMeta.startCol,
    dataRowCount,
    tableMeta.columnCount
  );

  const headers = Array.from({ length: tableMeta.columnCount }, (_, index) => {
    const rawHeader = tableMeta.headerValues?.[index];
    const normalized = String(rawHeader ?? "").trim();
    return normalized || `column_${index + 1}`;
  });

  return rows.map((rowValues) => {
    const rowObj = {};
    for (let index = 0; index < headers.length; index += 1) {
      rowObj[headers[index]] = Array.isArray(rowValues) ? rowValues[index] : null;
    }
    return rowObj;
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
  const APPLY_BATCH_SIZE = 1000;
  const MAX_COMMENT_LENGTH = 4000;

  for (let start = 0; start < results.length; start += APPLY_BATCH_SIZE) {
    const batch = results.slice(start, start + APPLY_BATCH_SIZE);

    await Excel.run(async (context) => {
      const worksheet = context.workbook.worksheets.getActiveWorksheet();

      for (const result of batch) {
        const cell = worksheet.getRange(result.address);
        // Use severityScore for heatmap coloring (falls back to failCount for compatibility)
        const severityScore = result.severityScore !== undefined ? result.severityScore : result.failCount;
        const color = heatmapColor(severityScore, maxSeverityScore);
        cell.format.fill.color = color;

        // Comments for failures only (comments are pre-cleared for the whole selected range).
        if (result.failCount > 0 && result.rowIndex > 0) {
          const rawComment = String(result.comment || "Validation failure");
          const safeComment = rawComment.length > MAX_COMMENT_LENGTH
            ? `${rawComment.slice(0, MAX_COMMENT_LENGTH - 1)}…`
            : rawComment;
          worksheet.comments.add(result.address, safeComment, Excel.ContentType.plain);
        }
      }

      await context.sync();
    });
  }
}

async function buildFailureExportRows() {
  const currentWorkbookName = String(getWorkbookName() || "").trim();
  const currentSheetName = String(lastValidationSourceSheetName || "").trim();
  const exceptionIdByAddress = new Map();

  for (const rawItem of lastTaggedCells || []) {
    const taggedCell = normalizeTaggedCellRecord(rawItem);
    if (!taggedCell) {
      continue;
    }

    const taggedWorkbook = String(taggedCell.workbook_name || "").trim();
    const taggedSheet = String(taggedCell.sheet_name || "").trim();
    const matchesWorkbook = !currentWorkbookName
      || !taggedWorkbook
      || taggedWorkbook === currentWorkbookName
      || taggedWorkbook === "__unknown_workbook__";
    const matchesSheet = !currentSheetName
      || !taggedSheet
      || taggedSheet === currentSheetName
      || taggedSheet === "__unknown_sheet__";

    if (!matchesWorkbook || !matchesSheet) {
      continue;
    }

    const normalizedAddress = String(taggedCell.address || "").replace(/\$/g, "").trim().toUpperCase();
    if (!normalizedAddress) {
      continue;
    }

    exceptionIdByAddress.set(normalizedAddress, String(taggedCell.exception_id || "").trim());
  }

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
      const normalizedResultAddress = String(result.address || "")
        .split("!")
        .pop()
        .replace(/\$/g, "")
        .trim()
        .toUpperCase();
      const taggedExceptionId = String(exceptionIdByAddress.get(normalizedResultAddress) || "").trim();
      const resultLevelExceptionId = String(result.exception_id || result.exceptionId || taggedExceptionId || "").trim();

      if (failedTests.length > 0) {
        for (const testMessage of failedTests) {
          let severity = "";
          let testId = "Unknown";
          let description = "";
          let testType = "";
          let exceptionId = resultLevelExceptionId;
          if (typeof testMessage === "string") {
            const rawMessage = String(testMessage || "").trim();
            const match = rawMessage.match(/^\[(.*?)\]\s+([A-Za-z0-9_]+):\s*(.*)$/);
            severity = match ? match[1] : "";
            testId = match ? match[2] : "Unknown";
            description = match ? match[3] : rawMessage;

            const exceptionMatch = rawMessage.match(/(?:Exception\s*ID|ExceptionID|EXC)[\s:=#-]*([A-Za-z0-9._-]+)/i);
            if (exceptionMatch && exceptionMatch[1]) {
              exceptionId = String(exceptionMatch[1]).trim();
            }
          } else if (typeof testMessage === "object" && testMessage !== null) {
            severity = String(testMessage.severity || "");
            testId = String(testMessage.testId || "Unknown");
            description = String(testMessage.description || "");
            testType = String(testMessage.testType || "");
            exceptionId = String(
              testMessage.exception_id
                || testMessage.exceptionId
                || testMessage.exceptionID
                || resultLevelExceptionId
                || ""
            ).trim();
          }
          dataRows.push({ umr: umrValue, testId, fieldName, value, severity, exceptionId, description, testType });
        }
      } else {
        dataRows.push({
          umr: umrValue,
          testId: "Unknown",
          fieldName,
          value,
          severity: "",
          exceptionId: resultLevelExceptionId,
          description: "",
          testType: "",
        });
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

    const headers = ["UMR", "Test ID", "Field Name", "Value", "Severity", "Exception ID", "Test Type", "Description"];
    const rowsForCsv = [headers, ...exportRows.map((row) => [
      row.umr,
      row.testId,
      row.fieldName,
      row.value,
      row.severity,
      row.exceptionId || "",
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

async function computeVisualisationKpisFromCurrentRun(exportRows) {
  const failedUmrs = new Set((exportRows || []).map((r) => String(r.umr || "").trim()).filter(Boolean));
  const failedFields = new Set((exportRows || []).map((r) => String(r.fieldName || "").trim()).filter(Boolean));
  const failedTests = new Set((exportRows || []).map((r) => String(r.testId || "").trim()).filter(Boolean));

  let totalSubmittedUmrs = null;
  let totalFields = null;

  try {
    await Excel.run(async (context) => {
      const workbook = context.workbook;
      const worksheet = lastValidationSourceSheetName
        ? workbook.worksheets.getItemOrNullObject(lastValidationSourceSheetName)
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

      const umrCol = resolveReferenceColumnIndex(header, lastValidationPack || currentPackSelection);
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

  const totalTests = Array.isArray(lastValidationExecutedTests) ? lastValidationExecutedTests.length : null;

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

async function saveResultsVersion() {
  const saveButton = document.getElementById("saveResultsVersion");
  if (!Array.isArray(lastValidationResults) || lastValidationResults.length === 0) {
    setStatus("No validation results to save. Please run validation first.", true);
    return;
  }

  const excelUserEmail = getExcelUserEmail();
  if (!excelUserEmail) {
    setStatus("Could not determine Excel user email.", true);
    return;
  }

  if (saveButton) {
    saveButton.disabled = true;
  }

  try {
    const activeSheetName = await getActiveSheetName();
    if (activeSheetName && lastValidationSourceSheetName && activeSheetName !== lastValidationSourceSheetName) {
      setStatus("Please run validation on the active sheet before saving a version.", true);
      return;
    }

    const { workbookName, sheetName } = await getCurrentResultsScope({ preferValidationSheet: true });
    const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
    if (!selectedPack) {
      throw new Error("Select a test pack before saving.");
    }

    await checkSavedResultsVersion();
    const viewedVersionContext = getViewedVersionContextForSheet(workbookName, sheetName);
    const isViewedVersionUpdate = Boolean(viewedVersionContext && Number(viewedVersionContext.versionId || 0));
    const isUpdate = savedResultsVersionExists || isViewedVersionUpdate;

    const selectedVersion = (savedVersionItems || []).find(
      (item) => Number(item?.id || 0) === Number(document.getElementById("savedVersions")?.value || 0)
    ) || (savedVersionItems[0] || null);
    const fallbackTimestamp = new Date(
      selectedVersion?.updated_at
      || selectedVersion?.updatedAt
      || selectedVersion?.created_at
      || selectedVersion?.createdAt
      || Date.now()
    ).toLocaleString();
    const suggestedName = String(
      viewedVersionContext?.versionName
      || selectedVersion?.version_name
      || selectedVersion?.versionName
      || ""
    ).trim() || `Report ${fallbackTimestamp}`;

    const requestedName = await promptForReportName(suggestedName);
    if (requestedName === null) {
      setStatus("Save cancelled.");
      return;
    }

    const versionName = String(requestedName || "").trim();
    if (!versionName) {
      setStatus("Save failed: report name cannot be blank.", true);
      return;
    }

    const failedTests = Array.isArray(lastValidationFailedTests)
      ? lastValidationFailedTests.map((item) => ({
          id: String(item?.id || item?.umr || ""),
          umr: String(item?.umr || ""),
          test_id: String(item?.test_id || ""),
        })).filter((item) => item.test_id)
      : [];
    const passedTests = Array.isArray(lastValidationPassedTests)
      ? lastValidationPassedTests.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    const passedUmrs = Array.isArray(lastValidationPassedUmrs)
      ? lastValidationPassedUmrs.map((item) => String(item || "").trim()).filter(Boolean)
      : [];

    const currentPackConfig = packConfigsByPack[selectedPack] || {};
    const mappedHeaders = currentPackConfig.fieldMappings
      || currentPackConfig.FieldMappings
      || currentPackConfig.columnMappings
      || {};

    const savedData = await buildCurrentSheetDataPayload();
    const taggedCells = getTaggedCellsForScope(workbookName, sheetName);
    const exportRows = await buildFailureExportRows();
    const computedKpis = await computeVisualisationKpisFromCurrentRun(exportRows);
    const kpisForSave = {
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
      computed_at: computedKpis.computed_at,
    };

    const requestUrl = isViewedVersionUpdate
      ? `${CONFIG.BACKEND_URL}/api/v1/results/versions/${Number(viewedVersionContext.versionId)}`
      : `${CONFIG.BACKEND_URL}/api/v1/results/versions`;
    const requestMethod = isViewedVersionUpdate ? "PUT" : "POST";

    if (isViewedVersionUpdate) {
      const expectedPack = String(viewedVersionContext?.testPack || "").trim().toLowerCase();
      if (expectedPack && expectedPack !== selectedPack) {
        throw new Error(`This viewed report is linked to '${expectedPack}'. Switch back to that pack to update it.`);
      }
    }

    const response = await fetch(requestUrl, {
      method: requestMethod,
      headers: {
        "Content-Type": "application/json",
        "X-Excel-User-Email": excelUserEmail,
      },
      body: JSON.stringify({
        workbook_name: workbookName,
        sheet_name: sheetName,
        test_pack: selectedPack,
        failed_tests: failedTests,
        passed_tests: passedTests,
        passed_umrs: passedUmrs,
        mapped_headers: mappedHeaders,
        saved_data: savedData,
        tagged_cells: taggedCells,
        version_name: versionName,
        kpis: kpisForSave,
        summary_metrics: kpisForSave,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const detail = formatBackendErrorDetail(errorData?.detail) || `HTTP ${response.status}`;
      throw new Error(detail);
    }

    await checkSavedResultsVersion();
    if (isViewedVersionUpdate) {
      appendDebugLog("Updated viewed saved version", {
        versionId: Number(viewedVersionContext.versionId),
        workbookName,
        sheetName,
        selectedPack,
      });
      setStatus(`Updated viewed report version ${Number(viewedVersionContext.versionId)}.`);
    } else {
      setStatus(isUpdate ? "Updated current results version." : "Saved current results version.");
    }
  } catch (error) {
    setStatus(`Save failed: ${error?.message || "Unexpected error"}`, true);
  } finally {
    if (saveButton) {
      saveButton.disabled = false;
    }
    updateActionButtons();
  }
}

async function deleteSelectedResultsVersion() {
  const deleteButton = document.getElementById("deleteResultsVersion");
  const select = document.getElementById("savedVersions");
  const selectedVersionId = Number(select?.value || 0);

  if (!selectedVersionId) {
    setStatus("Select a saved version to delete.", true);
    return;
  }

  const excelUserEmail = getExcelUserEmail();
  if (!excelUserEmail) {
    setStatus("Could not determine Excel user email.", true);
    return;
  }

  if (deleteButton) {
    deleteButton.disabled = true;
  }

  try {
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/results/versions/${selectedVersionId}`, {
      method: "DELETE",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const detail = formatBackendErrorDetail(errorData?.detail) || `HTTP ${response.status}`;
      throw new Error(detail);
    }

    removeViewedVersionContextByVersionId(selectedVersionId);
    await refreshActiveViewedVersionContext();
    await checkSavedResultsVersion();
    setStatus(`Deleted saved version ${selectedVersionId}.`);
  } catch (error) {
    setStatus(`Delete failed: ${error?.message || "Unexpected error"}`, true);
  } finally {
    if (deleteButton) {
      deleteButton.disabled = false;
    }
    updateActionButtons();
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

    const computedKpis = await computeVisualisationKpisFromCurrentRun(exportRows);
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
      const excelUserEmail = getExcelUserEmail();
      const selectedPack = String(lastValidationPack || document.getElementById("testPacks")?.value || "").trim().toLowerCase();
      if (excelUserEmail && selectedPack) {
        const { workbookName, sheetName } = await getCurrentResultsScope();
        const comparisonQuery = new URLSearchParams({
          workbook_name: workbookName,
          sheet_name: sheetName,
          test_pack: selectedPack,
        });

        const comparisonResponse = await fetch(`${CONFIG.BACKEND_URL}/api/v1/results/versions/comparison?${comparisonQuery.toString()}`, {
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
      exceptionId: r.exceptionId || '',
      description: r.description || ''
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

    /* ── Nav ── */
    .nav { display:flex; align-items:center; gap:16px; padding:0 24px; height:52px; background:var(--nav-bg); border-bottom:1px solid #1e2028; position:sticky; top:0; z-index:100; }
    .nav-logo { display:flex; align-items:center; gap:8px; color:#fff; font-size:14px; font-weight:600; letter-spacing:-.2px; text-decoration:none; }
    .nav-logo img { width:20px; height:20px; object-fit:contain; border-radius:5px; flex-shrink:0; }
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
    .stat-delta { margin-top:8px; font-size:11px; font-weight:600; }
    .stat-delta.up { color:#b91c1c; }
    .stat-delta.down { color:#15803d; }
    .stat-delta.neutral { color:var(--text-3); }

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

    .sparkline-wrap { width:100%; margin:0; min-height:0; }
    .sparkline-empty { text-align:center; color:var(--text-3); padding:24px 0; }
    .sparkline-svg { display:block; width:100%; height:auto; }
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

  <!-- KPI strip -->
  <div class="stat-grid">
    ${kpis.map((k,i)=>{
      const accent = getKpiAccent(k);
      const sub = getKpiSub(k);
      const delta = k?.delta || null;
      const deltaHtml = delta
        ? `<div class="stat-delta ${escapeHtml(delta.tone || 'neutral')}">${escapeHtml(delta.label || 'No change')} vs previous run</div>`
        : `<div class="stat-delta neutral">No previous run comparison</div>`;
      return `<div class="stat-card ${accent}"><div class="stat-label">${escapeHtml(k.title)}</div><div class="stat-value">${escapeHtml(k.value)}</div><div class="stat-sub">${sub}</div>${deltaHtml}</div>`;
    }).join('')}
  </div>

  <!-- Flow diagram -->
  ${sankeyBase64 ? `
  <div class="panel" id="trend-panel" style="margin-bottom:16px">
    <div class="panel-header">
      <div><div class="panel-title">Test Flow Overview</div><div class="panel-subtitle">Test flow representing the outcomes of the validation run from source to result</div></div>
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
        <div class="panel-subtitle">Top 10 by failure count on a test, field and submission level (broken down by severity)</div>
      </div>
      <div class="tab-group" id="bar-controls"></div>
    </div>
    <div class="panel-body">
      <div class="chart-wrap" id="bar-container"></div>
    </div>
  </div>

  <div class="panel" style="margin-bottom:16px">
    <div class="panel-header">
      <div><div class="panel-title">Historic Test Pass Rate</div><div class="panel-subtitle">The test pass rate over time for saved report versions associated with the current test pack</div></div>
    </div>
    <div class="panel-body" style="padding:0 0 2px;">
      <div class="sparkline-wrap" id="trend-chart"></div>
    </div>
  </div>

  <!-- Failure detail table -->
  <div class="panel">
    <div class="panel-header">
      <div>
        <div class="panel-title">Failure Detail</div>
        <div class="panel-subtitle">Complete failure analysis for full transparency into each validation failure</div>
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
          <th>Exception ID</th>
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
  const trendRows = ${trendJson};
  const labels = { test: 'Test', trade: 'Field', umr: 'Submission' };

  function renderTrendChart() {
    const container = document.getElementById('trend-chart');
    const panel = document.getElementById('trend-panel');
    if (!container) return;
    const rows = (trendRows || [])
      .map((row) => ({
        date: new Date(row.created_at || row.updated_at || Date.now()),
        testPassedPct: Number(row.test_passed_pct),
        submissionsPassedPct: Number.isFinite(Number(row.submissions_failed_pct))
          ? (100 - Number(row.submissions_failed_pct))
          : Number.NaN,
        fieldsPassedPct: Number.isFinite(Number(row.fields_failed_pct))
          ? (100 - Number(row.fields_failed_pct))
          : Number.NaN,
        versionName: String(row.version_name || "").trim(),
        workbook: String(row.workbook_name || ''),
        sheet: String(row.sheet_name || ''),
        isCurrent: Boolean(row.is_current),
      }))
      .filter((row) => {
        const hasAnyMetric = Number.isFinite(row.testPassedPct)
          || Number.isFinite(row.submissionsPassedPct)
          || Number.isFinite(row.fieldsPassedPct);
        return hasAnyMetric && row.date instanceof Date && !Number.isNaN(row.date.getTime());
      })
      .sort((a, b) => a.date.getTime() - b.date.getTime());

    if (rows.length <= 2) {
      if (panel) panel.style.display = 'none';
      return;
    }

    if (panel) panel.style.display = '';

    const visibleRows = rows
      .slice()
      .sort((a, b) => b.date.getTime() - a.date.getTime())
      .slice(0, 5)
      .sort((a, b) => a.date.getTime() - b.date.getTime());

    if (!visibleRows.length) {
      container.innerHTML = '<div class="sparkline-empty">No saved historical pass-rate data available.</div>';
      return;
    }

    const width = 1200;
    const height = 320;
    const pad = { top: 40, right: 40, bottom: 64, left: 60 };
    const pointCount = visibleRows.length;
    const xSpan = Math.max(1, width - pad.left - pad.right);

    const xForIndex = (index) => {
      if (pointCount <= 1) {
        return pad.left + (xSpan / 2);
      }
      return pad.left + ((index / (pointCount - 1)) * xSpan);
    };

    const xFor = (row) => xForIndex(visibleRows.indexOf(row));
    const yFor = (value) => pad.top + ((100 - value) / 100) * (height - pad.top - pad.bottom);
    const escapeSvgText = (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    const buildSeriesRows = (metricKey) => visibleRows.filter((row) => Number.isFinite(row[metricKey]));
    const buildSeriesPoints = (metricKey) => buildSeriesRows(metricKey)
      .map((row) => xFor(row).toFixed(2) + ',' + yFor(row[metricKey]).toFixed(2))
      .join(' ');

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
        legend +
        verticalLines +
        tickLines +
        linePaths +
        circles +
        xAxisLabels +
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
    const max = Math.max(...rows.map(r => r.total), 1);

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
        '<div class="bar-track">' +
          '<div class="bar-fill" style="width:' + barPct + '%">' +
            '<div class="bar-seg warn" style="width:' + warningPct + '%" title="Warning: ' + (r.WARNING || 0) + '"></div>' +
            '<div class="bar-seg error" style="width:' + errorPct + '%" title="Error: ' + (r.ERROR || 0) + '"></div>' +
            '<div class="bar-seg critical" style="width:' + criticalPct + '%" title="Critical: ' + (r.CRITICAL || 0) + '"></div>' +
          '</div>' +
        '</div>' +
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
    renderTrendChart();
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

async function generateTemplate() {
  const button = document.getElementById("generateTemplate");
  const backendUrl = CONFIG.BACKEND_URL;
  const excelUserEmail = getExcelUserEmail();
  let generatedSheetName = null;

  if (!button) return;

  try {
    button.disabled = true;
    setStatus("Generating template...");

    // Get the selected test pack and territory
    const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
    const selectedTerritory = String(document.getElementById("territory")?.value || "").trim();

    if (!selectedPack) {
      throw new Error("Please select a test pack first");
    }

    if (!selectedTerritory) {
      throw new Error("Please select a territory first");
    }

    // Fetch template headers from backend
    const response = await fetch(
      `${backendUrl}/api/v1/generate-template?test_pack=${encodeURIComponent(selectedPack)}&territory=${encodeURIComponent(selectedTerritory)}`,
      {
        method: "GET",
        headers: {
          "X-Excel-User-Email": excelUserEmail,
        },
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const templateData = await response.json();
    let headers = templateData.headers || [];

    if (headers.length === 0) {
      throw new Error("No fields available for this pack and territory");
    }

    // Apply aliases from current pack configuration if available
    const currentPackConfig = packConfigsByPack[selectedPack];
    const aliases = currentPackConfig?.aliases || {};
    
    // Replace header keys with their aliases where configured
    headers = headers.map((header) => {
      // Check if this header has an alias mapped to it (value is the original header, key is the alias)
      for (const [aliasKey, aliasValue] of Object.entries(aliases)) {
        if (aliasValue === header) {
          return aliasKey; // Use the alias key instead of the original header
        }
      }
      return header; // Use original header if no alias found
    });

    // Create new worksheet and add template
    await Excel.run(async (context) => {
      const workbook = context.workbook;
      const sheets = workbook.worksheets;

      // Create a new worksheet with a name based on the pack and territory
      generatedSheetName = `${formatPackLabel(selectedPack)} - ${selectedTerritory}`.substring(0, 31);
      const newSheet = sheets.add(generatedSheetName);

      // Calculate the range for all header columns
      const lastCol = columnToA1(headers.length - 1);
      const headerRangeAddress = `A1:${lastCol}1`;
      
      // Add headers to the first row
      const headerRange = newSheet.getRange(headerRangeAddress);
      headerRange.values = [headers];

      // Format the header row
      headerRange.format.font.bold = true;
      headerRange.format.fill.color = "#ffffff";
      headerRange.format.font.color = "#000000";

      // Auto-fit columns
      headerRange.format.autofitColumns();

      // Activate the new sheet
      newSheet.activate();

      await context.sync();
    });

    setStatus(`Template generated with ${headers.length} fields in new sheet: ${generatedSheetName}`);
    
    // Save current pack configuration state before sheet switch
    try {
      await persistPackConfigStateForScope({
        scope: currentSheetPackConfigScope,
        persistToServer: true,
        showValidationError: false,
      });
    } catch (error) {
      reportFrontendError("Could not save configuration before sheet switch", error, { showStatus: false });
    }
    
    // Give the sheet activation and sync process time to complete, then ensure Configuration tab is visible
    await new Promise(resolve => setTimeout(resolve, 250));
    
    // Keep taskpane open and ensure Configuration tab is active
    const configTab = document.getElementById("tabConfiguration");
    if (configTab) {
      configTab.click();
    }
    
    // Try to show the taskpane if it's been hidden
    try {
      if (typeof Office?.addin?.show === "function") {
        await Office.addin.show();
      }
    } catch {
      // Best effort only
    }
  } catch (error) {
    setStatus(`Template generation failed: ${error?.message || "Unexpected error"}`, true);
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function estimateFieldMapping() {
  const button = document.getElementById("estimateFieldMapping");
  const excelUserEmail = getExcelUserEmail();
  const backendUrl = CONFIG.BACKEND_URL;

  if (!button) return;

  try {
    button.disabled = true;
    setStatus("Extracting headers and estimating field mapping...");

    // Get the selected test pack and territory
    const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
    const selectedTerritory = getSelectedTerritoryValue();

    if (!selectedPack) {
      throw new Error("Please select a test pack first");
    }

    if (!selectedTerritory) {
      throw new Error("Please select a territory first");
    }

    // Extract headers from the active sheet
    const sheetContext = await resolveValidationRangeMeta();
    if (!sheetContext) {
      throw new Error("Could not extract headers from active sheet");
    }

    const headerValues = sheetContext.headerValues || [];
    if (headerValues.length === 0) {
      throw new Error("No headers found on the active sheet");
    }

    // Normalize header values to strings
    const normalizedHeaders = headerValues.map((h) => String(h || "").trim()).filter(Boolean);
    if (normalizedHeaders.length === 0) {
      throw new Error("No non-empty headers found on the active sheet");
    }

    // Call backend to estimate field mapping
    const { estimateFieldMapping: estimateFieldMappingApi } = window.TaskpanePacks || {};
    if (!estimateFieldMappingApi) {
      throw new Error("Field mapping estimation service not available");
    }

    const estimationResult = await estimateFieldMappingApi(excelUserEmail, selectedPack, selectedTerritory, normalizedHeaders);

    if (!estimationResult) {
      throw new Error("No estimation result returned from server");
    }

    // Merge estimation results into pack config
    await mergeEstimationIntoParkConfig(selectedPack, estimationResult);

    setStatus(
      `Field mapping estimated: ${estimationResult.matched_count || 0} matched, ${estimationResult.unmatched_count || 0} unmatched`,
      false
    );
  } catch (error) {
    let errorMessage = "Unexpected error";
    if (error instanceof Error) {
      errorMessage = error.message;
    } else if (typeof error === "string") {
      errorMessage = error;
    } else if (error && typeof error === "object") {
      errorMessage = error.detail || error.message || String(error);
    }
    setStatus(`Field mapping estimation failed: ${errorMessage}`, true);
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function mergeEstimationIntoParkConfig(testPack, estimationResult) {
  const normalizedPack = String(testPack || "").trim().toLowerCase();
  if (!normalizedPack) {
    return;
  }

  const packConfigEditor = document.getElementById("packConfigs");
  if (!packConfigEditor) {
    return;
  }

  // Parse current pack config
  let currentConfig;
  try {
    currentConfig = parsePackConfigInput(packConfigEditor.value, normalizedPack);
  } catch {
    currentConfig = getDefaultPackConfig(normalizedPack);
  }

  // Helper to normalize field names (strip non-alphanumeric, lowercase)
  const normalizeForComparison = (value) => String(value || "").trim().toLowerCase().replace(/[^a-z0-9]/g, "");

  // Filter estimated mappings - only keep if normalized header differs from normalized field
  const estimatedAliases = estimationResult.estimated_mappings || {};
  const filteredEstimates = {};
  for (const [header, schemaField] of Object.entries(estimatedAliases)) {
    const normalizedHeader = normalizeForComparison(header);
    const normalizedField = normalizeForComparison(schemaField);
    
    // Only store if they differ after normalization
    if (normalizedHeader !== normalizedField) {
      filteredEstimates[header] = schemaField;
    }
  }

  // Preserve existing aliases and only fill in blank ones
  const mergedAliases = {
    ...filteredEstimates,
    ...(currentConfig.aliases || {}),
  };

  // Update the config
  const updatedConfig = {
    ...currentConfig,
    aliases: mergedAliases,
  };

  // Format and set the textarea
  packConfigEditor.value = JSON.stringify(updatedConfig, null, 2);

  // Trigger input event to update any bindings
  packConfigEditor.dispatchEvent(new Event("input", { bubbles: true }));
  schedulePackConfigStatePersist({ delayMs: 0, persistToServer: true, showValidationError: true, showSaveError: true });
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

  await persistPackConfigStateForScope({ persistToServer: true, showValidationError: true });

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
    lastValidationFailedTests = [];
    lastValidationPassedTests = [];
    lastValidationPack = selectedPack;
    clearPersistedValidationResults();

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
    const executedTestIds = new Set();
    const failedTestIds = new Set();
    const failedEntryByKey = new Map();
    const umrsInData = new Set();  // Track all UMRs seen in data
    const failedUmrs = new Set();  // Track UMRs that had failures
    const coverageWarnings = new Set();
    const referenceColumnIndex = resolveReferenceColumnIndex(selectionMeta.headerValues, selectedPack);
    const workbookNameForScope = getWorkbookName() || "__unknown_workbook__";
    const sheetNameForScope = selectionMeta.sheetName || "__unknown_sheet__";

    const storedExceptions = await fetchStoredExceptionsForAutoTagging(excelUserEmail);
    const exceptionLookup = buildLinkedExceptionLookup(storedExceptions);

    const alreadyTaggedAddresses = new Set();
    for (const rawItem of getTaggedCellsForScope(workbookNameForScope, sheetNameForScope)) {
      const taggedCell = normalizeTaggedCellRecord(rawItem);
      if (!taggedCell) {
        continue;
      }
      alreadyTaggedAddresses.add(String(taggedCell.address || "").replace(/\$/g, "").trim().toUpperCase());
    }

    const autoTaggedCellByAddress = new Map();

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
        for (const [testName, testData] of Object.entries(tests)) {
          executedTestNames.add(`${packName}.${testName}`);
          const testId = String(testData?.testCode || `${packName}.${testName}`).trim();
          if (testId) {
            executedTestIds.add(testId);
            if (Number(testData?.failedRows || 0) > 0) {
              failedTestIds.add(testId);
            }
          }
        }
      }

      for (const result of results) {
        if (!(Number(result?.rowIndex) > 0 && Number(result?.failCount) > 0)) {
          continue;
        }

        const localRowIndex = Number(result.rowIndex) - 1;
        const failedMessages = Array.isArray(result.failedTests) ? result.failedTests : [];
        const rowValues = localRowIndex >= 0 ? chunkValues[localRowIndex] : null;
        const umrValue = (
          referenceColumnIndex >= 0 && Array.isArray(rowValues)
            ? String(rowValues[referenceColumnIndex] ?? "").trim()
            : ""
        );

        if (umrValue) {
          umrsInData.add(umrValue);
          failedUmrs.add(umrValue);
        }

        const fieldName = String(selectionMeta.headerValues?.[Number(result?.columnIndex)] || "").trim();
        const exceptionLookupKey = `${normalizeExceptionMatchValue(umrValue)}::${normalizeExceptionMatchValue(fieldName)}`;
        const matchedException = exceptionLookup.get(exceptionLookupKey);
        const normalizedResultAddress = String(result?.address || "")
          .split("!")
          .pop()
          .replace(/\$/g, "")
          .trim()
          .toUpperCase();

        if (
          matchedException
          && normalizedResultAddress
          && !alreadyTaggedAddresses.has(normalizedResultAddress)
          && !autoTaggedCellByAddress.has(normalizedResultAddress)
        ) {
          autoTaggedCellByAddress.set(normalizedResultAddress, {
            address: normalizedResultAddress,
            exception_id: matchedException.exception_id,
            comment: `Exception tagged: ${matchedException.exception_id}`,
            fill_color: EXCEPTION_TAG_FILL,
            previous_fill_color: "",
            sheet_name: sheetNameForScope,
            workbook_name: workbookNameForScope,
            tagged_at: new Date().toISOString(),
          });
        }

        for (const failedMessage of failedMessages) {
          const testId = extractTestIdFromFailureMessage(failedMessage);
          if (!testId) {
            continue;
          }
          failedTestIds.add(testId);
          const dedupeKey = `${umrValue}::${testId}`;
          if (!failedEntryByKey.has(dedupeKey)) {
            failedEntryByKey.set(dedupeKey, {
              umr: umrValue,
              id: umrValue,
              test_id: testId,
            });
          }
        }
      }

      setStatus(`Applying results for chunk ${chunkIndex + 1}/${totalChunks}...`);
      await applyResultsToSheet(results, maxSeverityScore);

      failedCount += results.filter((item) => item.rowIndex > 0 && item.failCount > 0).length;
    }

    let autoTaggedCount = 0;
    if (autoTaggedCellByAddress.size > 0) {
      const autoTaggedCells = Array.from(autoTaggedCellByAddress.values());
      const fillByAddress = await getCurrentFillColorsForAddresses(autoTaggedCells.map((item) => item.address));
      const tagsWithPreviousFill = autoTaggedCells.map((item) => ({
        ...item,
        previous_fill_color: String(fillByAddress.get(item.address) || item.previous_fill_color || "").trim(),
      }));

      await applyExceptionTagsToSheet(tagsWithPreviousFill);
      lastTaggedCells = mergeTaggedCells(lastTaggedCells, tagsWithPreviousFill);
      persistValidationResults();

      const tagsByException = new Map();
      for (const taggedCell of tagsWithPreviousFill) {
        const exceptionId = String(taggedCell.exception_id || "").trim();
        if (!exceptionId) {
          continue;
        }
        if (!tagsByException.has(exceptionId)) {
          tagsByException.set(exceptionId, []);
        }
        tagsByException.get(exceptionId).push(taggedCell);
      }

      for (const [exceptionId, taggedCells] of tagsByException.entries()) {
        const addresses = taggedCells.map((item) => item.address);
        await syncTaggedCellsToBackend(
          exceptionId,
          addresses,
          sheetNameForScope,
          workbookNameForScope,
          taggedCells
        );
      }

      autoTaggedCount = tagsWithPreviousFill.length;
    }

    const packName = testPacks[0];
    lastValidationResults = aggregatedResults;
    lastValidationExecutedTests = Array.from(executedTestNames).sort();
    lastValidationFailedTests = Array.from(failedEntryByKey.values());
    lastValidationPassedTests = Array.from(executedTestIds).filter((testId) => !failedTestIds.has(testId)).sort();
    lastValidationPassedUmrs = Array.from(umrsInData).filter((umr) => !failedUmrs.has(umr)).sort();
    await reapplyTaggedCellsForScope(workbookNameForScope, sheetNameForScope);
    persistValidationResults();
    await checkSavedResultsVersion();
    const warningText = Array.from(coverageWarnings).join(" | ");
    const statusMessage = `Validation complete with ${packName}: ${failedCount} cells failed at least one test.`;
    const autoTagStatus = autoTaggedCount > 0
      ? ` Auto-tagged ${autoTaggedCount} cell(s) from linked exceptions.`
      : "";
    setStatus(
      warningText ? `${statusMessage}${autoTagStatus} Warning: ${warningText}.` : `${statusMessage}${autoTagStatus}`,
      Boolean(warningText)
    );
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
