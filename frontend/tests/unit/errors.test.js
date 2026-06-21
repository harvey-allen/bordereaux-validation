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

test("error helpers recover when both launch and main shells are hidden", () => {
  const makeClassList = (initial = []) => {
    const values = new Set(initial);
    return {
      add(value) {
        values.add(value);
      },
      remove(value) {
        values.delete(value);
      },
      contains(value) {
        return values.has(value);
      },
    };
  };

  const elements = {
    launchScreen: { classList: makeClassList(["hidden"]) },
    mainAppShell: { classList: makeClassList(["hidden"]) },
    launchTitle: { textContent: "" },
    launchSubtitle: { textContent: "" },
    launchGetStarted: { classList: makeClassList(), disabled: true },
  };

  const win = loadBrowserScript(
    "modules/taskpane/errors.js",
    {},
    {
      document: {
        getElementById(id) {
          return elements[id] || null;
        },
      },
    }
  );

  const recovered = win.TaskpaneErrors.recoverBlankTaskpane("Recovered from blank view");

  assert.equal(recovered, true);
  assert.equal(elements.launchScreen.classList.contains("hidden"), false);
  assert.equal(elements.mainAppShell.classList.contains("hidden"), true);
  assert.equal(elements.launchTitle.textContent, "Something went wrong");
  assert.equal(elements.launchSubtitle.textContent, "Recovered from blank view");
  assert.equal(elements.launchGetStarted.classList.contains("hidden"), true);
});
