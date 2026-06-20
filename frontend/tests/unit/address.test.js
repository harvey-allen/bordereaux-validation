const test = require("node:test");
const assert = require("node:assert/strict");

const { loadBrowserScript } = require("../helpers/load-browser-script");

test("address helpers convert columns correctly", () => {
  const win = loadBrowserScript("modules/taskpane/address.js");

  assert.equal(win.TaskpaneAddress.excelColToNumber("A"), 1);
  assert.equal(win.TaskpaneAddress.excelColToNumber("AA"), 27);
  assert.equal(win.TaskpaneAddress.numberToExcelCol(1), "A");
  assert.equal(win.TaskpaneAddress.numberToExcelCol(27), "AA");
});

test("address helpers parse a single cell", () => {
  const win = loadBrowserScript("modules/taskpane/address.js");

  assert.deepEqual(
    JSON.parse(JSON.stringify(win.TaskpaneAddress.parseCell("$b$12"))),
    { col: 2, row: 12 }
  );
  assert.equal(win.TaskpaneAddress.parseCell("not-a-cell"), null);
});

test("address helpers parse excel ranges into individual addresses", () => {
  const win = loadBrowserScript("modules/taskpane/address.js");

  assert.deepEqual(
    JSON.parse(JSON.stringify(win.TaskpaneAddress.parseExcelAddress("Sheet1!A1:B2"))),
    ["A1", "B1", "A2", "B2"]
  );
  assert.deepEqual(
    JSON.parse(JSON.stringify(win.TaskpaneAddress.parseExcelAddress("Sheet1!C5"))),
    ["C5"]
  );
  assert.deepEqual(JSON.parse(JSON.stringify(win.TaskpaneAddress.parseExcelAddress("invalid"))), []);
});
