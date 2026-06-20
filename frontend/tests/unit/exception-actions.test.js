const test = require("node:test");
const assert = require("node:assert/strict");

const { loadBrowserScript } = require("../helpers/load-browser-script");

function createMockElement(tagName = "div") {
  const element = {
    tagName: String(tagName || "div").toUpperCase(),
    className: "",
    style: {},
    dataset: {},
    children: [],
    value: "",
    textContent: "",
    title: "",
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    addEventListener() {},
    querySelector() {
      return null;
    },
  };

  Object.defineProperty(element, "innerHTML", {
    get() {
      return this._innerHTML || "";
    },
    set(value) {
      this._innerHTML = String(value || "");
      this.children = [];
    },
  });

  return element;
}

test("renderExceptionList only shows exception id and status", async () => {
  const exceptionListContainer = createMockElement("div");
  const exceptionList = createMockElement("div");
  const noExceptionsMessage = createMockElement("div");

  const elementsById = {
    exceptionListContainer,
    exceptionList,
    noExceptionsMessage,
  };

  const document = {
    getElementById(id) {
      return elementsById[id] || null;
    },
    createElement(tagName) {
      return createMockElement(tagName);
    },
  };

  const fetch = async () => ({
    ok: true,
    json: async () => ({
      exceptions: [
        {
          exception_id: "EXC-001",
          status: "in progress",
          description: "Long description that should not be shown",
          linked_field: "Field A",
          linked_umr: "UMR-1",
        },
      ],
    }),
  });

  const win = loadBrowserScript("modules/taskpane/exception-actions.js", {
    document,
    fetch,
  });

  await win.TaskpaneExceptionActions.renderExceptionList({
    getExcelUserEmail: () => "user@example.com",
    CONFIG: { BACKEND_URL: "https://example.test" },
    truncateText: (text) => text,
    setStatus() {},
  });

  assert.equal(exceptionListContainer.style.display, "block");
  assert.equal(noExceptionsMessage.style.display, "none");
  assert.equal(exceptionList.children.length, 1);

  const item = exceptionList.children[0];
  const info = item.children[0];
  assert.equal(info.children.length, 2);
  assert.equal(info.children[0].className, "exception-id");
  assert.equal(info.children[0].textContent, "EXC-001");
  assert.equal(info.children[1].className, "exception-status");
  assert.equal(info.children[1].textContent, "In Progress");
  assert.equal(JSON.stringify(item).includes("Long description"), false);
});