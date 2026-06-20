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
    focus() {
      this._focused = true;
    },
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

test("resetExceptionFormToCreateMode clears edit state and returns create mode", () => {
  const exceptionIdInput = createMockElement("input");
  exceptionIdInput.value = "EXC-100";

  const exceptionFieldInput = createMockElement("select");
  exceptionFieldInput.value = "Premium";

  const exceptionUmrInput = createMockElement("input");
  exceptionUmrInput.value = "UMR-100";

  const exceptionDescriptionInput = createMockElement("textarea");
  exceptionDescriptionInput.value = "Existing exception";

  const exceptionStatusInput = createMockElement("select");
  exceptionStatusInput.value = "in progress";

  const exceptionFormTitle = createMockElement("h4");
  exceptionFormTitle.textContent = "Edit Exception";

  const createExceptionBtn = createMockElement("button");
  createExceptionBtn.textContent = "Update";
  createExceptionBtn.title = "Update the selected exception or record.";
  createExceptionBtn.dataset.editMode = "true";
  createExceptionBtn.dataset.originalExceptionId = "EXC-100";

  const newExceptionBtnContainer = createMockElement("div");
  newExceptionBtnContainer.style.display = "block";

  const elementsById = {
    exceptionIdInput,
    exceptionFieldInput,
    exceptionUmrInput,
    exceptionDescriptionInput,
    exceptionStatusInput,
    exceptionFormTitle,
    createExceptionBtn,
    newExceptionBtnContainer,
  };

  const document = {
    getElementById(id) {
      return elementsById[id] || null;
    },
  };

  const win = loadBrowserScript("modules/taskpane/exception-actions.js", {
    document,
  });

  win.TaskpaneExceptionActions.resetExceptionFormToCreateMode({}, { clearFields: true });

  assert.equal(exceptionIdInput.value, "");
  assert.equal(exceptionFieldInput.value, "");
  assert.equal(exceptionUmrInput.value, "");
  assert.equal(exceptionDescriptionInput.value, "");
  assert.equal(exceptionStatusInput.value, "to do");
  assert.equal(exceptionFormTitle.textContent, "Create New Exception");
  assert.equal(createExceptionBtn.textContent, "Create");
  assert.equal(createExceptionBtn.title, "Create a new exception record.");
  assert.equal(createExceptionBtn.dataset.editMode, "false");
  assert.equal(createExceptionBtn.dataset.originalExceptionId, undefined);
  assert.equal(newExceptionBtnContainer.style.display, "none");
  assert.equal(exceptionIdInput._focused, true);
});

test("editException shows New Exception button only in update mode", async () => {
  const exceptionIdInput = createMockElement("input");
  const exceptionFieldInput = createMockElement("select");
  const exceptionUmrInput = createMockElement("input");
  const exceptionDescriptionInput = createMockElement("textarea");
  const exceptionStatusInput = createMockElement("select");
  const exceptionFormTitle = createMockElement("h4");
  const createExceptionBtn = createMockElement("button");
  const newExceptionBtnContainer = createMockElement("div");

  const elementsById = {
    exceptionIdInput,
    exceptionFieldInput,
    exceptionUmrInput,
    exceptionDescriptionInput,
    exceptionStatusInput,
    exceptionFormTitle,
    createExceptionBtn,
    newExceptionBtnContainer,
    testPacks: { value: "risk_and_premium" },
  };

  const document = {
    getElementById(id) {
      return elementsById[id] || null;
    },
    createElement(tagName) {
      return createMockElement(tagName);
    },
    querySelector() {
      return exceptionIdInput;
    },
  };

  const fetch = async (url) => {
    if (String(url).includes("/api/v1/rules-engine")) {
      return {
        ok: true,
        json: async () => ({ rules: [{ target_column: "Premium" }] }),
      };
    }

    return {
      ok: true,
      json: async () => ({
        exceptions: [
          {
            exception_id: "EXC-123",
            linked_field: "Premium",
            linked_umr: "UMR-123",
            description: "Needs update",
            status: "in progress",
          },
        ],
      }),
    };
  };

  const win = loadBrowserScript("modules/taskpane/exception-actions.js", {
    document,
    fetch,
  });

  await win.TaskpaneExceptionActions.editException(
    {
      getExcelUserEmail: () => "user@example.com",
      CONFIG: { BACKEND_URL: "https://example.test" },
      setStatus() {},
    },
    "EXC-123"
  );

  assert.equal(createExceptionBtn.dataset.editMode, "true");
  assert.equal(newExceptionBtnContainer.style.display, "block");
});