const test = require("node:test");
const assert = require("node:assert/strict");

const { loadBrowserScript } = require("../helpers/load-browser-script");

test("viewSelectedSavedVersion falls back to tabular launch when workbook import is unsupported", async () => {
  const button = { disabled: false };
  const document = {
    getElementById(id) {
      if (id === "viewSavedVersion") {
        return button;
      }
      return null;
    },
  };

  const fetch = async () => ({
    ok: true,
    json: async () => ({
      id: 42,
      sheet_key_id: 15,
      test_pack: "bordereaux",
      version_name: "Snapshot 1",
      excel_file_base64: "ZmFrZS14bHN4",
      excel_source_sheet_name: "Sheet1",
      mapped_headers: { A: "field_a" },
      saved_data: [{ A: "value" }],
      pack_config: {},
    }),
  });

  const win = loadBrowserScript("modules/taskpane/version-actions.js", {
    document,
    fetch,
  });

  let workbookLaunchCalls = 0;
  let tabularLaunchCalls = 0;
  let runValidationCalls = 0;
  const statuses = [];

  const deps = {
    CONFIG: { BACKEND_URL: "https://example.test" },
    versionHelpers: {
      computeCurrentScopeVersionState: () => ({ exists: false, createdAt: null }),
      deriveSavedReportHeaders: () => ["A"],
    },
    getSelectedSavedVersionItem: () => ({ id: 42, current_scope: false }),
    getExcelUserEmail: () => "user@example.com",
    getCurrentResultsScope: async () => ({ workbookName: "Book.xlsx", sheetName: "Sheet1" }),
    getSelectedPack: () => "bordereaux",
    appendDebugLog() {},
    formatBackendErrorDetail: () => null,
    setSavedResultsVersionState: () => {},
    renderSavedVersionsDropdown: () => {},
    updateSavedResultsInfo: () => {},
    updateSaveButtonLabel: () => {},
    setStatus: (message) => {
      statuses.push(String(message || ""));
    },
    launchSavedWorkbookSheetFromBase64: async () => {
      workbookLaunchCalls += 1;
      throw new Error("The operation failed because the source contains one or more unsupported features. Features currently unsupported on this platform are Comment, Slicer, Chart, and PivotTable.");
    },
    launchSavedReportSheet: async () => {
      tabularLaunchCalls += 1;
      return "Fallback Sheet";
    },
    applySavedVersionPackConfiguration: async () => ({}),
    persistPackConfigurationForSheet: async () => {},
    setViewedVersionContextForSheet: () => {},
    refreshActiveViewedVersionContext: async () => {},
    refreshVersionStateForActiveSheet: async () => {},
    getWorkbookName: () => "Book.xlsx",
    updateActionButtons: () => {},
    runValidation: async () => {
      runValidationCalls += 1;
    },
  };

  await win.TaskpaneVersionActions.viewSelectedSavedVersion(deps);

  assert.equal(workbookLaunchCalls, 1);
  assert.equal(tabularLaunchCalls, 1);
  assert.equal(runValidationCalls, 0);
  assert.equal(button.disabled, false);
});

test("viewSelectedSavedVersion creates notice fallback when workbook import is unsupported and no tabular data exists", async () => {
  const button = { disabled: false };
  const document = {
    getElementById(id) {
      if (id === "viewSavedVersion") {
        return button;
      }
      return null;
    },
  };

  const fetch = async () => ({
    ok: true,
    json: async () => ({
      id: 43,
      sheet_key_id: 16,
      test_pack: "bordereaux",
      version_name: "Snapshot 2",
      excel_file_base64: "ZmFrZS14bHN4",
      excel_source_sheet_name: "Sheet1",
      mapped_headers: {},
      saved_data: [],
      pack_config: {},
    }),
  });

  const win = loadBrowserScript("modules/taskpane/version-actions.js", {
    document,
    fetch,
  });

  let workbookLaunchCalls = 0;
  let tabularLaunchCalls = 0;
  let launchedPayload = null;

  const deps = {
    CONFIG: { BACKEND_URL: "https://example.test" },
    versionHelpers: {
      computeCurrentScopeVersionState: () => ({ exists: false, createdAt: null }),
      deriveSavedReportHeaders: () => [],
    },
    getSelectedSavedVersionItem: () => ({ id: 43, current_scope: false }),
    getExcelUserEmail: () => "user@example.com",
    getCurrentResultsScope: async () => ({ workbookName: "Book.xlsx", sheetName: "Sheet1" }),
    getSelectedPack: () => "bordereaux",
    appendDebugLog() {},
    formatBackendErrorDetail: () => null,
    setSavedResultsVersionState: () => {},
    renderSavedVersionsDropdown: () => {},
    updateSavedResultsInfo: () => {},
    updateSaveButtonLabel: () => {},
    setStatus: () => {},
    launchSavedWorkbookSheetFromBase64: async () => {
      workbookLaunchCalls += 1;
      throw new Error("The operation failed because the source contains one or more unsupported features. Features currently unsupported on this platform are Comment, Slicer, Chart, and PivotTable.");
    },
    launchSavedReportSheet: async ({ savedData, mappedHeaders }) => {
      tabularLaunchCalls += 1;
      launchedPayload = { savedData, mappedHeaders };
      return "Fallback Notice Sheet";
    },
    applySavedVersionPackConfiguration: async () => ({}),
    persistPackConfigurationForSheet: async () => {},
    setViewedVersionContextForSheet: () => {},
    refreshActiveViewedVersionContext: async () => {},
    getWorkbookName: () => "Book.xlsx",
    updateActionButtons: () => {},
  };

  await win.TaskpaneVersionActions.viewSelectedSavedVersion(deps);

  assert.equal(workbookLaunchCalls, 1);
  assert.equal(tabularLaunchCalls, 1);
  assert.equal(Array.isArray(launchedPayload.savedData), true);
  assert.equal(launchedPayload.savedData.length, 1);
  assert.equal(typeof launchedPayload.savedData[0].Notice, "string");
  assert.equal(button.disabled, false);
});

test("viewSelectedSavedVersion restores matching sheet-key pack configuration from saved payload", async () => {
  const button = { disabled: false };
  const document = {
    getElementById(id) {
      if (id === "viewSavedVersion") {
        return button;
      }
      return null;
    },
  };

  const fetch = async () => ({
    ok: true,
    json: async () => ({
      id: 44,
      sheet_key_id: 17,
      test_pack: "claims",
      version_name: "Snapshot 3",
      mapped_headers: { UMR: "Unique Market Reference (UMR)" },
      saved_data: [{ UMR: "A-1" }],
      pack_config: { ID: "legacy-id" },
      worksheet_snapshot: {
        test_pack: "bordereaux",
        pack_config: {
          ID: "Unique Market Reference (UMR)",
          territory: "UK",
        },
        mapped_headers: { UMR: "Unique Market Reference (UMR)" },
        saved_data: [{ UMR: "A-1" }],
      },
    }),
  });

  const win = loadBrowserScript("modules/taskpane/version-actions.js", {
    document,
    fetch,
  });

  const applyCalls = [];
  const persistCalls = [];

  const deps = {
    CONFIG: { BACKEND_URL: "https://example.test" },
    versionHelpers: {
      computeCurrentScopeVersionState: () => ({ exists: false, createdAt: null }),
      deriveSavedReportHeaders: () => ["UMR"],
    },
    getSelectedSavedVersionItem: () => ({ id: 44, current_scope: false }),
    getExcelUserEmail: () => "user@example.com",
    getCurrentResultsScope: async () => ({ workbookName: "Book.xlsx", sheetName: "Sheet1" }),
    getSelectedPack: () => "bordereaux",
    appendDebugLog() {},
    formatBackendErrorDetail: () => null,
    setSavedResultsVersionState: () => {},
    renderSavedVersionsDropdown: () => {},
    updateSavedResultsInfo: () => {},
    updateSaveButtonLabel: () => {},
    setStatus: () => {},
    launchSavedReportSheet: async () => "Snapshot 3",
    applySavedVersionPackConfiguration: async (testPack, packConfig) => {
      applyCalls.push({ testPack, packConfig });
      return packConfig;
    },
    persistPackConfigurationForSheet: async (testPack, packConfig, sheetName) => {
      persistCalls.push({ testPack, packConfig, sheetName });
    },
    setViewedVersionContextForSheet: () => {},
    refreshActiveViewedVersionContext: async () => {},
    refreshVersionStateForActiveSheet: async () => {},
    getWorkbookName: () => "Book.xlsx",
    updateActionButtons: () => {},
  };

  await win.TaskpaneVersionActions.viewSelectedSavedVersion(deps);

  assert.equal(applyCalls.length, 1);
  assert.equal(applyCalls[0].testPack, "claims");
  assert.deepEqual(applyCalls[0].packConfig, {
    ID: "legacy-id",
  });

  assert.equal(persistCalls.length, 1);
  assert.equal(persistCalls[0].testPack, "claims");
  assert.equal(persistCalls[0].sheetName, "Snapshot 3");
  assert.deepEqual(persistCalls[0].packConfig, {
    ID: "legacy-id",
  });
  assert.equal(button.disabled, false);
});
