const test = require("node:test");
const assert = require("node:assert/strict");

const { loadBrowserScript } = require("../helpers/load-browser-script");

test("error helpers build consistent error messages", () => {
  const win = loadBrowserScript("modules/taskpane/errors.js");

  assert.equal(
    win.TaskpaneErrors.buildFrontendErrorMessage("Frontend error", new Error("boom")),
    "Frontend error: boom"
  );
  assert.equal(
    win.TaskpaneErrors.buildFrontendErrorMessage("Frontend error", { message: "bad request" }),
    "Frontend error: bad request"
  );
});

test("error helpers suppress known Office context errors", () => {
  const win = loadBrowserScript("modules/taskpane/errors.js");

  assert.equal(
    win.TaskpaneErrors.shouldSuppressFrontendError("Invalid API call in the current context"),
    true
  );
  assert.equal(win.TaskpaneErrors.shouldSuppressFrontendError("Some other error"), false);
});
