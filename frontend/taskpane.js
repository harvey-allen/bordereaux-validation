/**
 * Heatmap color gradient: no failures=white, then level 1-10 as light→dark red.
 * Uses severity score instead of simple failure count for more nuanced coloring.
 * Severity levels: INFO=0, WARNING=1, ERROR=2, CRITICAL=3
 */
const taskpaneConstants = window.TaskpaneConstants || {};
const DEFAULT_EXCEL_EMAIL = String(taskpaneConstants.DEFAULT_EXCEL_EMAIL || "harveyallen2001@gmail.com");
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
const APP_LOGO_URL = `${window.location.origin}/assets/AXIOS.png`;
const EXCEPTION_TAG_FILL = String(taskpaneConstants.EXCEPTION_TAG_FILL || "#dbeafe");
const MAX_EXCEL_SHEET_NAME_LENGTH = Number(taskpaneConstants.MAX_EXCEL_SHEET_NAME_LENGTH || 31);
const DEBUG_LOG_STORAGE_KEY = String(taskpaneConstants.DEBUG_LOG_STORAGE_KEY || "bordereaux_validator_debug_log");
const VIEWED_VERSION_CONTEXT_STORAGE_KEY = String(
  taskpaneConstants.VIEWED_VERSION_CONTEXT_STORAGE_KEY || "bordereaux_validator_viewed_version_context"
);
const PACK_CONFIG_STATE_STORAGE_KEY = String(
  taskpaneConstants.PACK_CONFIG_STATE_STORAGE_KEY || "bordereaux_validator_pack_config_state"
);
const FALLBACK_DISPLAY_NAME = String(taskpaneConstants.FALLBACK_DISPLAY_NAME || "there");

let availablePackOptions = [];
let currentSheetPackConfigScope = null;
let packConfigInputPersistTimer = null;
let activeSheetSyncSequence = 0;
let hasInitializedMainApp = false;

const {
  formatPackLabel,
  formatTestTypeLabel,
  populatePackSelect,
  loadSubscribedPackValues,
} = window.TaskpanePacks || {};

const taskpaneScopeHelpers = window.TaskpaneScope || {};
const taskpaneErrorHelpers = window.TaskpaneErrors || {};
const taskpaneDebugHelpers = window.TaskpaneDebug || {};
const taskpaneTaggedCellHelpers = window.TaskpaneTaggedCells || {};
const taskpaneAddressHelpers = window.TaskpaneAddress || {};
const taskpaneSheetRangeHelpers = window.TaskpaneSheetRange || {};
const taskpaneVersionHelpers = window.TaskpaneVersions || {};
const taskpaneVersionActionHelpers = window.TaskpaneVersionActions || {};
const taskpaneExceptionHelpers = window.TaskpaneExceptions || {};
const taskpaneExceptionActionHelpers = window.TaskpaneExceptionActions || {};
const taskpaneValidationActionHelpers = window.TaskpaneValidationActions || {};
const taskpaneVisualisationHelpers = window.TaskpaneVisualisation || {};
const taskpaneRulesEngineHelpers = window.TaskpaneRulesEngine || {};
const taskpaneExtractionHelpers = window.TaskpaneExtraction || {};

const storageHelpers = window.TaskpaneStorage || {};

function appendDebugLog(message, metadata = null) {
  taskpaneDebugHelpers.appendDebugLog(message, metadata);
}

function buildSheetScopeKey(workbookName, sheetName) {
  return taskpaneScopeHelpers.buildSheetScopeKey(workbookName, sheetName);
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
  return taskpaneErrorHelpers.buildFrontendErrorMessage(prefix, error);
}

function shouldSuppressFrontendError(error) {
  return taskpaneErrorHelpers.shouldSuppressFrontendError(error);
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
  restoreValidationResultsForScope(nextScope);
  updateActionButtons();
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
  return taskpaneDebugHelpers.getDebugLogs();
};

window.__bvClearDebugLogs = function __bvClearDebugLogs() {
  taskpaneDebugHelpers.clearDebugLogs();
};

/**
 * Persist all validation results to localStorage
 */
function persistValidationResults() {
  if (typeof storageHelpers.persist !== "function") {
    return;
  }
  const workbookName = currentSheetPackConfigScope?.workbookName || getWorkbookName() || "__unknown_workbook__";
  const sheetName = String(
    lastValidationSourceSheetName
      || currentSheetPackConfigScope?.sheetName
      || "__unknown_sheet__"
  ).trim() || "__unknown_sheet__";
  const scopeKey = buildSheetScopeKey(workbookName, sheetName);

  storageHelpers.persist({
    results: lastValidationResults,
    sourceSheetName: lastValidationSourceSheetName,
    executedTests: lastValidationExecutedTests,
    pack: lastValidationPack,
    failedTests: lastValidationFailedTests,
    passedTests: lastValidationPassedTests,
    passedUmrs: lastValidationPassedUmrs,
    taggedCells: lastTaggedCells,
  }, { scopeKey });
}

/**
 * Restore validation results from localStorage
 */
function restoreValidationResultsForScope(scope) {
  const workbookName = String(scope?.workbookName || "__unknown_workbook__").trim() || "__unknown_workbook__";
  const sheetName = String(scope?.sheetName || "__unknown_sheet__").trim() || "__unknown_sheet__";
  const scopeKey = buildSheetScopeKey(workbookName, sheetName);

  if (typeof storageHelpers.restore !== "function") {
    lastValidationResults = [];
    lastValidationSourceSheetName = null;
    lastValidationExecutedTests = [];
    lastValidationPack = null;
    lastValidationFailedTests = [];
    lastValidationPassedTests = [];
    lastValidationPassedUmrs = [];
    return false;
  }

  const persistData = storageHelpers.restore({ scopeKey });
  if (!persistData) {
    lastValidationResults = [];
    lastValidationSourceSheetName = null;
    lastValidationExecutedTests = [];
    lastValidationPack = null;
    lastValidationFailedTests = [];
    lastValidationPassedTests = [];
    lastValidationPassedUmrs = [];
    return false;
  }

  lastValidationResults = Array.isArray(persistData.results) ? persistData.results : [];
  lastValidationSourceSheetName = persistData.sourceSheetName || null;
  lastValidationExecutedTests = Array.isArray(persistData.executedTests) ? persistData.executedTests : [];
  lastValidationPack = persistData.pack || null;
  lastValidationFailedTests = Array.isArray(persistData.failedTests) ? persistData.failedTests : [];
  lastValidationPassedTests = Array.isArray(persistData.passedTests) ? persistData.passedTests : [];
  lastValidationPassedUmrs = Array.isArray(persistData.passedUmrs) ? persistData.passedUmrs : [];
  const restoredTaggedCells = Array.isArray(persistData.taggedCells) ? persistData.taggedCells : [];
  lastTaggedCells = mergeTaggedCells(lastTaggedCells, restoredTaggedCells);

  if (!lastValidationSourceSheetName && sheetName !== "__unknown_sheet__") {
    lastValidationSourceSheetName = sheetName;
  }

  return true;
}

/**
 * Clear persisted validation results from localStorage
 */
function clearPersistedValidationResultsForScope(scope) {
  const workbookName = String(scope?.workbookName || "__unknown_workbook__").trim() || "__unknown_workbook__";
  const sheetName = String(scope?.sheetName || "__unknown_sheet__").trim() || "__unknown_sheet__";
  const scopeKey = buildSheetScopeKey(workbookName, sheetName);

  if (typeof storageHelpers.clear !== "function") {
    return;
  }
  storageHelpers.clear({ scopeKey });
}

function normalizeTaggedCellRecord(item) {
  return taskpaneTaggedCellHelpers.normalizeTaggedCellRecord(item);
}

function mergeTaggedCells(existingItems, incomingItems) {
  return taskpaneTaggedCellHelpers.mergeTaggedCells(existingItems, incomingItems);
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
  taskpaneVersionHelpers.updateSaveButtonLabel(saveButton, savedResultsVersionExists, activeViewedVersionContext);
}

function renderSavedVersionsDropdown(items) {
  const select = document.getElementById("savedVersions");
  savedVersionItems = taskpaneVersionHelpers.renderSavedVersionsDropdown(select, items);
  updateActionButtons();
}

function getSelectedSavedVersionItem() {
  const selectedVersionId = Number(document.getElementById("savedVersions")?.value || 0);
  return taskpaneVersionHelpers.getSelectedSavedVersionItem(savedVersionItems, selectedVersionId);
}

function normalizeExcelSheetNameCandidate(rawName) {
  return taskpaneVersionHelpers.normalizeExcelSheetNameCandidate(rawName, MAX_EXCEL_SHEET_NAME_LENGTH);
}

async function createUniqueWorksheetName(baseName) {
  return taskpaneVersionHelpers.createUniqueWorksheetName(baseName, MAX_EXCEL_SHEET_NAME_LENGTH);
}

function toExcelCellValue(value) {
  return taskpaneVersionHelpers.toExcelCellValue(value);
}

function deriveSavedReportHeaders(savedData, mappedHeaders) {
  return taskpaneVersionHelpers.deriveSavedReportHeaders(savedData, mappedHeaders);
}

async function launchSavedReportSheet({ versionName, savedData, mappedHeaders }) {
  return taskpaneVersionHelpers.launchSavedReportSheet({
    versionName,
    savedData,
    mappedHeaders,
    maxSheetNameLength: MAX_EXCEL_SHEET_NAME_LENGTH,
    appendDebugLog,
  });
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
  await taskpaneVersionActionHelpers.viewSelectedSavedVersion(buildVersionActionDeps());
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

function formatDisplayNameFallbackFromEmail(email) {
  const localPart = String(email || "").trim().split("@")[0] || "";
  if (!localPart) {
    return FALLBACK_DISPLAY_NAME;
  }

  return localPart
    .replace(/[._-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase())
    .join(" ") || FALLBACK_DISPLAY_NAME;
}

function getExcelDisplayName() {
  let officeDisplayName = null;
  try {
    officeDisplayName = Office?.context?.userProfile?.displayName || null;
  } catch {
    officeDisplayName = null;
  }

  const normalized = String(officeDisplayName || "").trim();
  if (normalized) {
    return normalized;
  }

  return formatDisplayNameFallbackFromEmail(getExcelUserEmail());
}

function getFirstName(displayName) {
  const normalized = String(displayName || "").trim();
  if (!normalized) {
    return FALLBACK_DISPLAY_NAME;
  }

  return normalized.split(/\s+/)[0] || FALLBACK_DISPLAY_NAME;
}

async function isRecognizedExcelUser(excelUserEmail) {
  if (!excelUserEmail) {
    return {
      isRecognized: false,
      displayName: "",
    };
  }

  try {
    const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/subscription`, {
      method: "GET",
      headers: {
        "X-Excel-User-Email": excelUserEmail,
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return {
        isRecognized: false,
        displayName: "",
      };
    }

    const payload = await response.json().catch(() => ({}));
    const displayName = String(payload?.display_name || "").trim();
    return {
      isRecognized: Boolean(payload?.is_active),
      displayName,
    };
  } catch {
    return {
      isRecognized: false,
      displayName: "",
    };
  }
}

function activateConfigurationTab() {
  const configTab = document.getElementById("tabConfiguration");
  if (configTab) {
    configTab.click();
  }
}

function showMainTaskpane() {
  const launchScreen = document.getElementById("launchScreen");
  const mainAppShell = document.getElementById("mainAppShell");
  launchScreen?.classList.add("hidden");
  mainAppShell?.classList.remove("hidden");
  activateConfigurationTab();
}

async function bootstrapTaskpaneLaunchExperience() {
  const launchLogo = document.getElementById("launchLogo");
  const launchTitle = document.getElementById("launchTitle");
  const launchSubtitle = document.getElementById("launchSubtitle");
  const launchButton = document.getElementById("launchGetStarted");

  if (!launchTitle || !launchSubtitle || !launchButton) {
    await initializeTaskpaneApp();
    hasInitializedMainApp = true;
    return;
  }

  if (launchLogo) {
    launchLogo.src = APP_LOGO_URL;
  }

  launchButton.classList.add("hidden");
  launchButton.disabled = false;

  const excelUserEmail = getExcelUserEmail();
  const identity = await isRecognizedExcelUser(excelUserEmail);

  if (!identity.isRecognized) {
    launchTitle.textContent = "Account not identified";
    launchSubtitle.textContent = "please contact Axios to for support";
    return;
  }

  const displayName = identity.displayName || getExcelDisplayName();
  launchTitle.textContent = `Welcome, ${getFirstName(displayName)}!`;
  launchSubtitle.textContent = "";
  launchButton.classList.remove("hidden");

  launchButton.addEventListener("click", async () => {
    launchButton.disabled = true;
    try {
      if (!hasInitializedMainApp) {
        await initializeTaskpaneApp();
        hasInitializedMainApp = true;
      }
      showMainTaskpane();
    } catch (error) {
      reportFrontendError("Taskpane initialization failed", error);
      launchButton.disabled = false;
    }
  });
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
  await taskpaneExceptionActionHelpers.loadExceptions(buildExceptionActionDeps());
}

function normalizeExceptionMatchValue(value) {
  return taskpaneExceptionHelpers.normalizeExceptionMatchValue(value);
}

function buildLinkedExceptionLookup(exceptions) {
  return taskpaneExceptionHelpers.buildLinkedExceptionLookup(exceptions);
}

async function fetchStoredExceptionsForAutoTagging(excelUserEmail) {
  return taskpaneExceptionActionHelpers.fetchStoredExceptionsForAutoTagging(buildExceptionActionDeps(), excelUserEmail);
}

async function loadLinkedFieldsForExceptionModal() {
  await taskpaneExceptionActionHelpers.loadLinkedFieldsForExceptionModal(buildExceptionActionDeps());
}

function openExceptionModal() {
  taskpaneExceptionActionHelpers.openExceptionModal(buildExceptionActionDeps());
}

function closeExceptionModal() {
  taskpaneExceptionActionHelpers.closeExceptionModal(buildExceptionActionDeps());
}

async function renderExceptionList() {
  await taskpaneExceptionActionHelpers.renderExceptionList(buildExceptionActionDeps());
}

function escapeHtml(text) {
  return taskpaneExceptionHelpers.escapeHtml(text);
}

function truncateText(text, maxLength = 16) {
  return taskpaneExceptionHelpers.truncateText(text, maxLength);
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
  return taskpaneExceptionActionHelpers.splitTaggedCellsByException(buildExceptionActionDeps(), exceptionId);
}

async function unapplyDeletedExceptionFromWorkbook(exceptionId, removedTaggedCells, remainingTaggedCells) {
  await taskpaneExceptionActionHelpers.unapplyDeletedExceptionFromWorkbook(
    buildExceptionActionDeps(),
    exceptionId,
    removedTaggedCells,
    remainingTaggedCells
  );
}

async function getCurrentFillColorsForAddresses(addresses) {
  return taskpaneExceptionActionHelpers.getCurrentFillColorsForAddresses(buildExceptionActionDeps(), addresses);
}


async function createException() {
  await taskpaneExceptionActionHelpers.createException(buildExceptionActionDeps());
}

async function deleteException(exceptionId) {
  await taskpaneExceptionActionHelpers.deleteException(buildExceptionActionDeps(), exceptionId);
}

async function editException(exceptionId) {
  await taskpaneExceptionActionHelpers.editException(buildExceptionActionDeps(), exceptionId);
}

async function applyExceptionToCell() {
  await taskpaneExceptionActionHelpers.applyExceptionToCell(buildExceptionActionDeps());
}

function parseExcelAddress(address) {
  return taskpaneAddressHelpers.parseExcelAddress(address);
}

function parseCell(cellStr) {
  return taskpaneAddressHelpers.parseCell(cellStr);
}

function excelColToNumber(col) {
  return taskpaneAddressHelpers.excelColToNumber(col);
}

function numberToExcelCol(num) {
  return taskpaneAddressHelpers.numberToExcelCol(num);
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
  bootstrapTaskpaneLaunchExperience().catch((error) => {
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
  return taskpaneSheetRangeHelpers.columnToA1(colIndexZeroBased);
}

function buildAddressRow(globalRowZeroBased, startColZeroBased, columnCount) {
  return taskpaneSheetRangeHelpers.buildAddressRow(globalRowZeroBased, startColZeroBased, columnCount);
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

async function ensureValidationResultsLoadedForActiveSheet() {
  const activeScope = await getCurrentResultsScope();
  const activeSheetName = String(activeScope?.sheetName || "").trim();
  const loadedSheetName = String(lastValidationSourceSheetName || "").trim();
  const hasLoadedResults = Array.isArray(lastValidationResults) && lastValidationResults.length > 0;

  if (hasLoadedResults && loadedSheetName && loadedSheetName === activeSheetName) {
    return true;
  }

  restoreValidationResultsForScope(activeScope);
  updateActionButtons();

  return Array.isArray(lastValidationResults) && lastValidationResults.length > 0;
}

function buildVersionActionDeps() {
  return {
    CONFIG,
    versionHelpers: taskpaneVersionHelpers,
    formatBackendErrorDetail,
    getExcelUserEmail,
    getCurrentResultsScope,
    getSelectedPack: () => String(document.getElementById("testPacks")?.value || "").trim().toLowerCase(),
    renderSavedVersionsDropdown,
    updateSavedResultsInfo,
    updateActionButtons,
    setSavedResultsVersionState: (exists, createdAt) => {
      savedResultsVersionExists = Boolean(exists);
      savedResultsVersionCreatedAt = createdAt ? String(createdAt).trim() : null;
    },
    getSavedResultsVersionState: () => ({
      exists: savedResultsVersionExists,
      createdAt: savedResultsVersionCreatedAt,
    }),
    refreshActiveViewedVersionContext,
    updateSaveButtonLabel,
    getSavedVersionItems: () => savedVersionItems,
    getViewedVersionContextForSheet,
    promptForReportName,
    getLastValidationResults: () => lastValidationResults,
    getLastValidationSourceSheetName: () => lastValidationSourceSheetName,
    getActiveSheetName,
    setStatus,
    getWorkbookName,
    getLastValidationFailedTests: () => lastValidationFailedTests,
    getLastValidationPassedTests: () => lastValidationPassedTests,
    getLastValidationPassedUmrs: () => lastValidationPassedUmrs,
    getPackConfigsByPack: () => packConfigsByPack,
    buildCurrentSheetDataPayload,
    getTaggedCellsForScope,
    buildFailureExportRows,
    computeVisualisationKpisFromCurrentRun,
    appendDebugLog,
    getSelectedSavedVersionItem,
    launchSavedReportSheet,
    applySavedVersionPackConfiguration,
    persistPackConfigurationForSheet,
    setViewedVersionContextForSheet,
    runValidation,
    removeViewedVersionContextByVersionId,
  };
}

function buildExceptionActionDeps() {
  return {
    CONFIG,
    EXCEPTION_TAG_FILL,
    formatBackendErrorDetail,
    getExcelUserEmail,
    getWorkbookName,
    getActiveSheetName,
    parseExcelAddress,
    normalizeTaggedCellRecord,
    mergeTaggedCells,
    persistValidationResults,
    applyExceptionTagsToSheet,
    syncTaggedCellsToBackend,
    truncateText,
    setStatus,
    getLastTaggedCells: () => lastTaggedCells,
    setLastTaggedCells: (value) => {
      lastTaggedCells = Array.isArray(value) ? value : [];
    },
  };
}

function buildValidationActionDeps() {
  return {
    CONFIG,
    EXCEPTION_TAG_FILL,
    formatPackLabel,
    columnToA1,
    getExcelUserEmail,
    getSelectedTerritoryValue,
    resolveValidationRangeMeta,
    parsePackConfigInput,
    getDefaultPackConfig,
    withDefaultEnabledTests,
    estimateFieldMappingApi: (window.TaskpanePacks || {}).estimateFieldMapping,
    schedulePackConfigStatePersist,
    persistPackConfigStateForScope,
    reportFrontendError,
    getCurrentSheetPackConfigScope: () => currentSheetPackConfigScope,
    setStatus,
    getWorkbookName,
    clearPersistedValidationResultsForScope,
    clearCommentsInRange,
    readRangeValues,
    buildAddressRow,
    formatBackendErrorDetail,
    extractTestIdFromFailureMessage,
    getTaggedCellsForScope,
    normalizeTaggedCellRecord,
    buildLinkedExceptionLookup,
    fetchStoredExceptionsForAutoTagging,
    normalizeExceptionMatchValue,
    applyResultsToSheet,
    getCurrentFillColorsForAddresses,
    applyExceptionTagsToSheet,
    mergeTaggedCells,
    persistValidationResults,
    syncTaggedCellsToBackend,
    reapplyTaggedCellsForScope,
    checkSavedResultsVersion,
    getDevelopmentFetchDiagnostics,
    updateActionButtons,
    buildFailureExportRows,
    ensureValidationResultsLoadedForActiveSheet,
    resolveReferenceColumnIndex,
    getPackConfigsByPack: () => packConfigsByPack,
    setPackConfigForPack: (packName, config) => {
      const normalizedPack = String(packName || "").trim().toLowerCase();
      if (!normalizedPack) {
        return;
      }
      packConfigsByPack[normalizedPack] = config;
    },
    setCurrentPackSelection: (packName) => {
      currentPackSelection = String(packName || "").trim().toLowerCase() || null;
    },
    getLastValidationResults: () => lastValidationResults,
    setLastValidationResults: (value) => {
      lastValidationResults = Array.isArray(value) ? value : [];
    },
    setLastValidationSourceSheetName: (value) => {
      lastValidationSourceSheetName = value ? String(value).trim() : null;
    },
    setLastValidationExecutedTests: (value) => {
      lastValidationExecutedTests = Array.isArray(value) ? value : [];
    },
    setLastValidationPack: (value) => {
      lastValidationPack = value ? String(value).trim().toLowerCase() : null;
    },
    setLastValidationFailedTests: (value) => {
      lastValidationFailedTests = Array.isArray(value) ? value : [];
    },
    setLastValidationPassedTests: (value) => {
      lastValidationPassedTests = Array.isArray(value) ? value : [];
    },
    setLastValidationPassedUmrs: (value) => {
      lastValidationPassedUmrs = Array.isArray(value) ? value : [];
    },
    getLastTaggedCells: () => lastTaggedCells,
    setLastTaggedCells: (value) => {
      lastTaggedCells = Array.isArray(value) ? value : [];
    },
  };
}

function buildVisualisationDeps() {
  return {
    CONFIG,
    APP_LOGO_URL,
    formatPackLabel,
    getExcelUserEmail,
    getCurrentResultsScope,
    ensureValidationResultsLoadedForActiveSheet,
    buildFailureExportRows,
    resolveReferenceColumnIndex,
    setStatus,
    getSelectedPack: () => String(document.getElementById("testPacks")?.value || "").trim().toLowerCase(),
    getCurrentPackSelection: () => currentPackSelection,
    getLastValidationResults: () => lastValidationResults,
    getLastValidationSourceSheetName: () => lastValidationSourceSheetName,
    getLastValidationPack: () => lastValidationPack,
    getLastValidationExecutedTests: () => lastValidationExecutedTests,
  };
}

async function refreshVersionStateForActiveSheet() {
  await taskpaneVersionActionHelpers.refreshVersionStateForActiveSheet(buildVersionActionDeps());
}

async function checkSavedResultsVersion() {
  await taskpaneVersionActionHelpers.checkSavedResultsVersion(buildVersionActionDeps());
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
  return taskpaneSheetRangeHelpers.isCellEmpty(value);
}

function findNonEmptyBounds(values) {
  return taskpaneSheetRangeHelpers.findNonEmptyBounds(values);
}

async function resolveValidationRangeMeta() {
  return taskpaneSheetRangeHelpers.resolveValidationRangeMeta();
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
    clearPersistedValidationResultsForScope(
      currentSheetPackConfigScope
      || {
        workbookName: getWorkbookName() || "__unknown_workbook__",
        sheetName: tableMeta.sheetName || "__unknown_sheet__",
      }
    );
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
  return taskpaneSheetRangeHelpers.readRangeValues(startRow, startCol, rowCount, columnCount);
}

async function buildCurrentSheetDataPayload() {
  return taskpaneSheetRangeHelpers.buildCurrentSheetDataPayload();
}

async function clearCommentsInRange(startRow, startCol, rowCount, columnCount) {
  await taskpaneSheetRangeHelpers.clearCommentsInRange(startRow, startCol, rowCount, columnCount);
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

function buildExtractionDeps() {
  return {
    ensureValidationResultsLoadedForActiveSheet,
    buildFailureExportRows,
    setStatus,
    getLastValidationResults: () => lastValidationResults,
  };
}

async function extractValidationResults() {
  await taskpaneExtractionHelpers.extractValidationResults(buildExtractionDeps());
}

async function computeVisualisationKpisFromCurrentRun(exportRows) {
  return taskpaneVisualisationHelpers.computeVisualisationKpisFromCurrentRun(buildVisualisationDeps(), exportRows);
}

async function saveResultsVersion() {
  await taskpaneVersionActionHelpers.saveResultsVersion(buildVersionActionDeps());
}

async function deleteSelectedResultsVersion() {
  await taskpaneVersionActionHelpers.deleteSelectedResultsVersion(buildVersionActionDeps());
}

async function visualiseValidationResults() {
  await taskpaneVisualisationHelpers.visualiseValidationResults(buildVisualisationDeps());
}

async function openRulesEngine() {
  await taskpaneRulesEngineHelpers.openRulesEngine({
    CONFIG,
    APP_LOGO_URL,
    formatPackLabel,
    setStatus,
  });
}

async function generateTemplate() {
  await taskpaneValidationActionHelpers.generateTemplate(buildValidationActionDeps());
}

async function estimateFieldMapping() {
  await taskpaneValidationActionHelpers.estimateFieldMapping(buildValidationActionDeps());
}

async function mergeEstimationIntoParkConfig(testPack, estimationResult) {
  await taskpaneValidationActionHelpers.mergeEstimationIntoParkConfig(
    buildValidationActionDeps(),
    testPack,
    estimationResult
  );
}

async function runValidation() {
  await taskpaneValidationActionHelpers.runValidation(buildValidationActionDeps());
}
