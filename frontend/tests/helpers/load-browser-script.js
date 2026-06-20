const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function loadBrowserScript(relativeScriptPath, initialWindow = {}, extraGlobals = {}) {
  const filePath = path.resolve(__dirname, "..", "..", relativeScriptPath);
  const code = fs.readFileSync(filePath, "utf8");

  const providedDocument = extraGlobals.document || initialWindow.document;
  const context = {
    ...initialWindow,
    window: initialWindow,
    document: providedDocument,
    console,
    Error,
    String,
    Math,
    parseInt,
    Date,
    URL,
    Map,
    Set,
    ...extraGlobals,
  };

  vm.runInNewContext(code, context, { filename: filePath });
  return context.window;
}

module.exports = {
  loadBrowserScript,
};
