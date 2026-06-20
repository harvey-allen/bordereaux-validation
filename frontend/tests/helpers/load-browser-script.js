const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function loadBrowserScript(relativeScriptPath, initialWindow = {}) {
  const filePath = path.resolve(__dirname, "..", "..", relativeScriptPath);
  const code = fs.readFileSync(filePath, "utf8");

  const context = {
    ...initialWindow,
    window: initialWindow,
    console,
    Error,
    String,
    Math,
    parseInt,
  };

  vm.runInNewContext(code, context, { filename: filePath });
  return context.window;
}

module.exports = {
  loadBrowserScript,
};
