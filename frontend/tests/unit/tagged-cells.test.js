const test = require("node:test");
const assert = require("node:assert/strict");

const { loadBrowserScript } = require("../helpers/load-browser-script");

test("tagged cell helper normalizes shape and defaults", () => {
  const win = loadBrowserScript("modules/taskpane/tagged-cells.js", {
    TaskpaneConstants: { EXCEPTION_TAG_FILL: "#abc123" },
  });

  const normalized = win.TaskpaneTaggedCells.normalizeTaggedCellRecord({
    address: " a1 ",
    exceptionId: "EX-1",
    comment: "",
    fillColor: "",
    previousFillColor: "#ffffff",
    sheetName: "Sheet 1",
    workbookName: "Book.xlsx",
  });

  assert.equal(normalized.address, "A1");
  assert.equal(normalized.exception_id, "EX-1");
  assert.equal(normalized.comment, "Exception tagged: EX-1");
  assert.equal(normalized.fill_color, "#abc123");
  assert.equal(normalized.previous_fill_color, "#ffffff");
  assert.equal(normalized.sheet_name, "Sheet 1");
  assert.equal(normalized.workbook_name, "Book.xlsx");
});

test("tagged cell helper merges and overwrites matching scope keys", () => {
  const win = loadBrowserScript("modules/taskpane/tagged-cells.js");

  const merged = win.TaskpaneTaggedCells.mergeTaggedCells(
    [
      { address: "A1", exception_id: "EX-1", sheet_name: "Sheet", workbook_name: "Book" },
      { address: "B2", exception_id: "EX-2", sheet_name: "Sheet", workbook_name: "Book" },
    ],
    [
      { address: "A1", exception_id: "EX-3", sheet_name: "Sheet", workbook_name: "Book" },
      { address: "C3", exception_id: "EX-4", sheet_name: "Sheet", workbook_name: "Book" },
      null,
    ]
  );

  const byAddress = Object.fromEntries(merged.map((row) => [row.address, row.exception_id]));
  assert.deepEqual(byAddress, { A1: "EX-3", B2: "EX-2", C3: "EX-4" });
});
