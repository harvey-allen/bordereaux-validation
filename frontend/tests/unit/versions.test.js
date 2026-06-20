const test = require("node:test");
const assert = require("node:assert/strict");

const { loadBrowserScript } = require("../helpers/load-browser-script");

function createSelectDocument() {
  return {
    createElement(tagName) {
      if (tagName !== "option") {
        return {};
      }
      return {
        value: "",
        textContent: "",
        dataset: {},
      };
    },
  };
}

function createSelectElement() {
  const options = [];
  return {
    options,
    selectedIndex: -1,
    innerHTML: "keep",
    appendChild(option) {
      options.push(option);
    },
  };
}

test("version helpers update labels and dropdown values", () => {
  const win = loadBrowserScript(
    "modules/taskpane/versions.js",
    {},
    { document: createSelectDocument() }
  );

  const saveButton = { textContent: "" };
  win.TaskpaneVersions.updateSaveButtonLabel(saveButton, false, null);
  assert.equal(saveButton.textContent, "Save Report");
  win.TaskpaneVersions.updateSaveButtonLabel(saveButton, true, null);
  assert.equal(saveButton.textContent, "Update Report");

  const select = createSelectElement();
  const items = win.TaskpaneVersions.renderSavedVersionsDropdown(select, [
    { id: 10, current_scope: true, version_name: "April Release" },
    { id: 11, currentScope: false, updated_at: "2026-01-02T00:00:00Z" },
  ]);

  assert.equal(items.length, 2);
  assert.equal(select.options.length, 2);
  assert.equal(select.options[0].value, "10");
  assert.equal(select.options[0].dataset.currentScope, "true");
  assert.equal(select.selectedIndex, 0);
});

test("version helpers normalize values and derive headers", () => {
  const win = loadBrowserScript(
    "modules/taskpane/versions.js",
    {},
    { document: createSelectDocument() }
  );

  assert.equal(
    win.TaskpaneVersions.normalizeExcelSheetNameCandidate("  Risk/Board? [Q1]  ", 20),
    "Risk Board Q1"
  );
  assert.equal(win.TaskpaneVersions.toExcelCellValue({ a: 1 }), '{"a":1}');

  const circular = {};
  circular.me = circular;
  assert.equal(win.TaskpaneVersions.toExcelCellValue(circular), "[object Object]");

  const headers = win.TaskpaneVersions.deriveSavedReportHeaders(
    [
      { UMR: "u1", Premium: 10 },
      { UMR: "u2", Currency: "GBP" },
    ],
    { UMR: "Unique Market Reference" }
  );
  assert.deepEqual(JSON.parse(JSON.stringify(headers.sort())), ["Currency", "Premium", "UMR"]);

  const fallbackHeaders = win.TaskpaneVersions.deriveSavedReportHeaders([], {
    UMR: "Unique Market Reference",
    Premium: "",
  });
  assert.deepEqual(JSON.parse(JSON.stringify(fallbackHeaders.sort())), ["Premium", "Unique Market Reference"]);

  const state = win.TaskpaneVersions.computeCurrentScopeVersionState([
    { id: 1, current_scope: false },
    { id: 2, currentScope: true, updatedAt: "2026-06-19T12:00:00Z" },
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(state)), { exists: true, createdAt: "2026-06-19T12:00:00Z" });
});
