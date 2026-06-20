const test = require("node:test");
const assert = require("node:assert/strict");

const { loadBrowserScript } = require("../helpers/load-browser-script");

test("scope helpers build stable workbook/sheet keys", () => {
  const win = loadBrowserScript("modules/taskpane/scope.js");

  assert.equal(win.TaskpaneScope.buildSheetScopeKey("Workbook", "Sheet1"), "Workbook::Sheet1");
  assert.equal(
    win.TaskpaneScope.buildSheetScopeKey("  Workbook  ", "  Sheet  "),
    "Workbook::Sheet"
  );
  assert.equal(
    win.TaskpaneScope.buildSheetScopeKey("", ""),
    "__unknown_workbook__::__unknown_sheet__"
  );
});
