const test = require("node:test");
const assert = require("node:assert/strict");

const { loadBrowserScript } = require("../helpers/load-browser-script");

function createEscapingDocument() {
  return {
    createElement() {
      const node = { _text: "" };
      Object.defineProperty(node, "textContent", {
        get() {
          return this._text;
        },
        set(value) {
          this._text = String(value || "");
          this.innerHTML = this._text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
        },
      });
      return node;
    },
  };
}

test("exception helpers escape and truncate text deterministically", () => {
  const win = loadBrowserScript(
    "modules/taskpane/exception-helpers.js",
    {},
    { document: createEscapingDocument() }
  );

  assert.equal(win.TaskpaneExceptions.escapeHtml('<b>hello & "goodbye"</b>'), "&lt;b&gt;hello &amp; &quot;goodbye&quot;&lt;/b&gt;");
  assert.equal(win.TaskpaneExceptions.truncateText("ABCDEFGHIJ", 5), "ABCDE...");
  assert.equal(win.TaskpaneExceptions.truncateText("", 5), "");
});

test("exception helpers build linked lookup and ignore invalid rows", () => {
  const win = loadBrowserScript(
    "modules/taskpane/exception-helpers.js",
    {},
    { document: createEscapingDocument() }
  );

  const lookup = win.TaskpaneExceptions.buildLinkedExceptionLookup([
    { exception_id: "EX-1", linked_field: "Premium", linked_umr: " UMR-1 " },
    { exception_id: "EX-2", linked_field: "Premium", linked_umr: "umr-1" },
    { exception_id: "", linked_field: "Premium", linked_umr: "UMR-1" },
    { exception_id: "EX-3", test_id: "Amount", linked_umr: "UMR-2" },
  ]);

  assert.equal(lookup.size, 2);
  assert.deepEqual(
    JSON.parse(JSON.stringify(lookup.get("umr-1::premium"))),
    { exception_id: "EX-1", linked_field: "Premium", linked_umr: "UMR-1" }
  );
  assert.deepEqual(
    JSON.parse(JSON.stringify(lookup.get("umr-2::amount"))),
    { exception_id: "EX-3", linked_field: "Amount", linked_umr: "UMR-2" }
  );
});
