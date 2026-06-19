(function initTaskpaneExceptionActions(global) {
  async function loadExceptions(deps) {
    try {
      const excelUserEmail = deps.getExcelUserEmail();
      if (!excelUserEmail) return;

      const response = await fetch(`${deps.CONFIG.BACKEND_URL}/api/v1/exceptions`, {
        method: "GET",
        headers: { "X-Excel-User-Email": excelUserEmail },
        cache: "no-store",
      });
      if (!response.ok) return;

      const payload = await response.json().catch(() => ({ exceptions: [] }));
      const exceptions = Array.isArray(payload?.exceptions) ? payload.exceptions : [];

      const exceptionSelect = document.getElementById("exceptionSelect");
      if (exceptionSelect) {
        exceptionSelect.innerHTML = "";
        if (exceptions.length === 0) {
          const option = document.createElement("option");
          option.value = "";
          option.textContent = "No exceptions available";
          exceptionSelect.appendChild(option);
        } else {
          const defaultOption = document.createElement("option");
          defaultOption.value = "";
          defaultOption.textContent = "Select an exception...";
          exceptionSelect.appendChild(defaultOption);
          for (const exc of exceptions) {
            const option = document.createElement("option");
            option.value = exc.exception_id;
            option.textContent = exc.exception_id;
            option.dataset.exceptionData = JSON.stringify(exc);
            exceptionSelect.appendChild(option);
          }
        }
      }
    } catch {
      // Silently fail
    }
  }

  async function fetchStoredExceptionsForAutoTagging(deps, excelUserEmail) {
    if (!excelUserEmail) return [];
    try {
      const response = await fetch(`${deps.CONFIG.BACKEND_URL}/api/v1/exceptions`, {
        method: "GET",
        headers: { "X-Excel-User-Email": excelUserEmail },
        cache: "no-store",
      });
      if (!response.ok) return [];
      const payload = await response.json().catch(() => ({ exceptions: [] }));
      return Array.isArray(payload?.exceptions) ? payload.exceptions : [];
    } catch {
      return [];
    }
  }

  async function loadLinkedFieldsForExceptionModal(deps) {
    try {
      const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
      const query = selectedPack ? `?test_pack=${encodeURIComponent(selectedPack)}` : "";

      const response = await fetch(`${deps.CONFIG.BACKEND_URL}/api/v1/rules-engine${query}`, {
        method: "GET",
        cache: "no-store",
      });
      if (!response.ok) return;

      const payload = await response.json().catch(() => ({ rules: [] }));
      const rules = Array.isArray(payload?.rules) ? payload.rules : [];
      const fields = Array.from(new Set(rules.map((r) => String(r?.target_column || "").trim()).filter(Boolean)));

      const fieldSelect = document.getElementById("exceptionFieldInput");
      if (fieldSelect) {
        const currentValue = fieldSelect.value;
        fieldSelect.innerHTML = "";
        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = "Select a field...";
        fieldSelect.appendChild(defaultOption);
        for (const fieldName of fields.sort((a, b) => a.localeCompare(b))) {
          const option = document.createElement("option");
          option.value = fieldName;
          option.textContent = fieldName;
          fieldSelect.appendChild(option);
        }
        fieldSelect.value = currentValue;
      }
    } catch {
      // Silently fail
    }
  }

  function openExceptionModal(deps) {
    const modal = document.getElementById("exceptionModal");
    if (modal) {
      modal.classList.add("active");
      loadLinkedFieldsForExceptionModal(deps);
      renderExceptionList(deps);
    }
  }

  function closeExceptionModal(deps) {
    void deps;
    const modal = document.getElementById("exceptionModal");
    if (modal) modal.classList.remove("active");
    document.getElementById("exceptionIdInput").value = "";
    document.getElementById("exceptionFieldInput").value = "";
    document.getElementById("exceptionUmrInput").value = "";
    document.getElementById("exceptionDescriptionInput").value = "";
    document.getElementById("exceptionStatusInput").value = "to do";
    const formTitle = document.getElementById("exceptionFormTitle");
    if (formTitle) formTitle.textContent = "Create New Exception";
    const createBtn = document.getElementById("createExceptionBtn");
    if (createBtn) {
      createBtn.textContent = "Create";
      createBtn.title = "Create a new exception record.";
      createBtn.dataset.editMode = "false";
      delete createBtn.dataset.originalExceptionId;
    }
  }

  async function renderExceptionList(deps) {
    try {
      const excelUserEmail = deps.getExcelUserEmail();
      if (!excelUserEmail) return;

      const response = await fetch(`${deps.CONFIG.BACKEND_URL}/api/v1/exceptions`, {
        method: "GET",
        headers: { "X-Excel-User-Email": excelUserEmail },
        cache: "no-store",
      });
      if (!response.ok) return;

      const payload = await response.json().catch(() => ({ exceptions: [] }));
      const exceptions = Array.isArray(payload?.exceptions) ? payload.exceptions : [];

      const container = document.getElementById("exceptionListContainer");
      const list = document.getElementById("exceptionList");
      const noMessage = document.getElementById("noExceptionsMessage");

      if (exceptions.length === 0) {
        if (container) container.style.display = "none";
        if (noMessage) noMessage.style.display = "block";
        return;
      }

      if (container) container.style.display = "block";
      if (noMessage) noMessage.style.display = "none";

      list.innerHTML = "";
      for (const exc of exceptions) {
        const item = document.createElement("div");
        item.className = "exception-item";

        const info = document.createElement("div");
        info.className = "exception-info";

        const idNode = document.createElement("div");
        idNode.className = "exception-id";
        idNode.textContent = exc.exception_id || "";

        const status = document.createElement("span");
        status.className = "exception-status";
        status.textContent = (exc.status || "").replace(/\b\w/g, (c) => c.toUpperCase());

        const descNode = document.createElement("div");
        descNode.className = "exception-desc";
        const fullDescription = String(exc.description || "");
        descNode.title = fullDescription;
        const firstDescriptionLine = fullDescription.split(/\r?\n/, 1)[0].trim();
        descNode.textContent = deps.truncateText(firstDescriptionLine, 16);

        info.appendChild(idNode);
        info.appendChild(status);
        info.appendChild(descNode);

        const linkedField = String(exc.linked_field || exc.test_id || "").trim();
        if (linkedField) {
          const fieldNode = document.createElement("div");
          fieldNode.style.fontSize = "11px";
          fieldNode.style.color = "#666";
          fieldNode.textContent = `Field: ${linkedField}`;
          info.appendChild(fieldNode);
        }

        const linkedUmr = String(exc.linked_umr || "").trim();
        if (linkedUmr) {
          const umrNode = document.createElement("div");
          umrNode.style.fontSize = "11px";
          umrNode.style.color = "#666";
          umrNode.textContent = `UMR: ${linkedUmr}`;
          info.appendChild(umrNode);
        }

        const actions = document.createElement("div");
        actions.className = "exception-actions";

        const editBtn = document.createElement("button");
        editBtn.className = "icon-btn";
        editBtn.type = "button";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", () => editException(deps, exc.exception_id));

        const deleteBtn = document.createElement("button");
        deleteBtn.className = "icon-btn";
        deleteBtn.type = "button";
        deleteBtn.style.color = "#dc2626";
        deleteBtn.textContent = "Delete";
        deleteBtn.addEventListener("click", () => deleteException(deps, exc.exception_id));

        actions.appendChild(editBtn);
        actions.appendChild(deleteBtn);
        item.appendChild(info);
        item.appendChild(actions);
        list.appendChild(item);
      }
    } catch {
      // Silently fail
    }
  }

  function splitTaggedCellsByException(deps, exceptionId) {
    const normalizedExceptionId = String(exceptionId || "").trim();
    const removed = [];
    const kept = [];

    for (const rawItem of deps.getLastTaggedCells() || []) {
      const taggedCell = deps.normalizeTaggedCellRecord(rawItem);
      if (!taggedCell) continue;
      if (taggedCell.exception_id === normalizedExceptionId) {
        removed.push(taggedCell);
      } else {
        kept.push(taggedCell);
      }
    }

    return { removed, kept };
  }

  async function unapplyDeletedExceptionFromWorkbook(deps, exceptionId, removedTaggedCells, remainingTaggedCells) {
    const normalizedExceptionId = String(exceptionId || "").trim();
    const activeWorkbookName = String(deps.getWorkbookName() || "").trim();

    const removedInActiveWorkbook = (removedTaggedCells || [])
      .map((item) => deps.normalizeTaggedCellRecord(item))
      .filter((item) => {
        if (!item) return false;
        if (!activeWorkbookName) return true;
        const taggedWorkbook = String(item.workbook_name || "").trim();
        return !taggedWorkbook || taggedWorkbook === activeWorkbookName || taggedWorkbook === "__unknown_workbook__";
      });

    if (!removedInActiveWorkbook.length) return;

    const remainingByCell = new Set();
    for (const rawItem of remainingTaggedCells || []) {
      const taggedCell = deps.normalizeTaggedCellRecord(rawItem);
      if (!taggedCell) continue;
      remainingByCell.add(`${taggedCell.sheet_name}::${taggedCell.address}`);
    }

    await Excel.run(async (context) => {
      const workbook = context.workbook;
      const worksheets = workbook.worksheets;
      worksheets.load("items/name");
      await context.sync();

      const worksheetByName = new Map();
      for (const sheet of worksheets.items) {
        worksheetByName.set(String(sheet.name || "").trim(), sheet);
      }

      const removedBySheet = new Map();
      for (const taggedCell of removedInActiveWorkbook) {
        const sheetName = String(taggedCell.sheet_name || "").trim();
        if (!sheetName) continue;
        if (!removedBySheet.has(sheetName)) removedBySheet.set(sheetName, []);
        removedBySheet.get(sheetName).push(taggedCell);
      }

      const sheetCommentsMap = new Map();
      const commentProxies = [];
      for (const [sheetName] of removedBySheet) {
        const worksheet = worksheetByName.get(sheetName);
        if (!worksheet) continue;
        const comments = worksheet.comments;
        comments.load("items");
        sheetCommentsMap.set(sheetName, comments);
      }
      await context.sync();

      const sheetCommentLookup = new Map();
      for (const [sheetName, comments] of sheetCommentsMap.entries()) {
        const entries = [];
        for (const comment of comments.items) {
          comment.load("content");
          const location = comment.getLocation();
          location.load("address");
          entries.push({ comment, location });
        }
        commentProxies.push({ sheetName, entries });
      }
      await context.sync();

      for (const { sheetName, entries } of commentProxies) {
        const lookup = new Map();
        for (const { comment, location } of entries) {
          const address = String(location.address || "");
          const cellPart = address.includes("!") ? address.split("!")[1] : address;
          lookup.set(String(cellPart || "").trim().toUpperCase(), comment);
        }
        sheetCommentLookup.set(sheetName, lookup);
      }

      for (const [sheetName, taggedCells] of removedBySheet.entries()) {
        const worksheet = worksheetByName.get(sheetName);
        if (!worksheet) continue;
        const commentLookup = sheetCommentLookup.get(sheetName) || new Map();

        for (const taggedCell of taggedCells) {
          const cellKey = `${sheetName}::${taggedCell.address}`;
          const hasRemainingTag = remainingByCell.has(cellKey);
          const range = worksheet.getRange(taggedCell.address);

          if (!hasRemainingTag) {
            const previousFill = String(taggedCell.previous_fill_color || "").trim();
            if (previousFill) {
              range.format.fill.color = previousFill;
            } else {
              range.format.fill.clear();
            }
          }

          const comment = commentLookup.get(taggedCell.address);
          if (!comment) continue;

          const originalLines = String(comment.content || "")
            .split(/\r?\n/)
            .map((line) => String(line || "").trim())
            .filter((line) => line.length > 0);

          const filteredLines = originalLines.filter(
            (line) => line !== `Exception tagged: ${normalizedExceptionId}`
          );

          if (filteredLines.length === originalLines.length) continue;

          if (filteredLines.length === 0) {
            comment.delete();
          } else {
            comment.content = filteredLines.join("\n");
          }
        }
      }

      await context.sync();
    });
  }

  async function getCurrentFillColorsForAddresses(deps, addresses) {
    void deps;
    const addressList = Array.isArray(addresses)
      ? addresses.map((address) => String(address || "").replace(/\$/g, "").trim().toUpperCase()).filter(Boolean)
      : [];

    if (!addressList.length) return new Map();

    return Excel.run(async (context) => {
      const worksheet = context.workbook.worksheets.getActiveWorksheet();
      const entries = [];

      for (const address of addressList) {
        const range = worksheet.getRange(address);
        range.format.fill.load("color");
        entries.push({ address, range });
      }

      await context.sync();

      const fillByAddress = new Map();
      for (const { address, range } of entries) {
        fillByAddress.set(address, String(range.format.fill.color || "").trim());
      }
      return fillByAddress;
    });
  }

  async function createException(deps) {
    const exceptionId = document.getElementById("exceptionIdInput").value.trim();
    const linkedField = document.getElementById("exceptionFieldInput").value.trim() || null;
    const linkedUmr = document.getElementById("exceptionUmrInput").value.trim() || null;
    const description = document.getElementById("exceptionDescriptionInput").value.trim();
    const status = document.getElementById("exceptionStatusInput").value;

    if (!exceptionId || !description) {
      deps.setStatus("Exception ID and Description are required.", true);
      return;
    }

    const excelUserEmail = deps.getExcelUserEmail();
    if (!excelUserEmail) {
      deps.setStatus("Could not determine Excel user email.", true);
      return;
    }

    const createBtn = document.getElementById("createExceptionBtn");
    const isEditMode = createBtn.dataset.editMode === "true";
    const originalExceptionId = createBtn.dataset.originalExceptionId;

    try {
      if (isEditMode) {
        const response = await fetch(
          `${deps.CONFIG.BACKEND_URL}/api/v1/exceptions/${encodeURIComponent(originalExceptionId)}`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json", "X-Excel-User-Email": excelUserEmail },
            body: JSON.stringify({ exception_id: exceptionId, linked_field: linkedField, linked_umr: linkedUmr, description, status }),
          }
        );
        if (!response.ok) {
          const errorPayload = await response.json().catch(() => ({}));
          deps.setStatus(`Error: ${errorPayload?.detail || "Failed to update exception"}`, true);
          return;
        }
        deps.setStatus("Exception updated successfully.");
      } else {
        const response = await fetch(`${deps.CONFIG.BACKEND_URL}/api/v1/exceptions`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Excel-User-Email": excelUserEmail },
          body: JSON.stringify({ exception_id: exceptionId, linked_field: linkedField, linked_umr: linkedUmr, description, status }),
        });
        if (!response.ok) {
          const errorPayload = await response.json().catch(() => ({}));
          deps.setStatus(`Error: ${errorPayload?.detail || "Failed to create exception"}`, true);
          return;
        }
        deps.setStatus("Exception created successfully.");
      }

      document.getElementById("exceptionIdInput").value = "";
      document.getElementById("exceptionFieldInput").value = "";
      document.getElementById("exceptionUmrInput").value = "";
      document.getElementById("exceptionDescriptionInput").value = "";
      document.getElementById("exceptionStatusInput").value = "to do";
      createBtn.textContent = "Create";
      createBtn.dataset.editMode = "false";
      createBtn.dataset.originalExceptionId = "";

      await renderExceptionList(deps);
      await loadExceptions(deps);
    } catch (error) {
      deps.setStatus(`Error: ${error?.message || "Unknown error"}`, true);
    }
  }

  async function deleteException(deps, exceptionId) {
    if (!String(exceptionId || "").trim()) {
      deps.setStatus("Missing exception ID.", true);
      return;
    }

    const excelUserEmail = deps.getExcelUserEmail();
    if (!excelUserEmail) {
      deps.setStatus("Could not determine Excel user email.", true);
      return;
    }

    const { removed: locallyRemovedTags, kept: locallyKeptTags } = splitTaggedCellsByException(deps, exceptionId);
    deps.setStatus(`Deleting exception '${exceptionId}'...`);

    try {
      const response = await fetch(
        `${deps.CONFIG.BACKEND_URL}/api/v1/exceptions/${encodeURIComponent(exceptionId)}`,
        { method: "DELETE", headers: { "X-Excel-User-Email": excelUserEmail } }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const detail = deps.formatBackendErrorDetail(errorData?.detail) || `HTTP ${response.status}`;
        deps.setStatus(`Failed to delete exception: ${detail}`, true);
        return;
      }

      const payload = await response.json().catch(() => ({}));
      const removedFromBackend = Array.isArray(payload?.removed_tagged_cells) ? payload.removed_tagged_cells : [];
      const tagsToRemoveFromSheet = removedFromBackend.length ? removedFromBackend : locallyRemovedTags;

      deps.setLastTaggedCells(locallyKeptTags);
      deps.persistValidationResults();

      try {
        await unapplyDeletedExceptionFromWorkbook(deps, exceptionId, tagsToRemoveFromSheet, deps.getLastTaggedCells());
      } catch {
        // Best effort only
      }

      deps.setStatus("Exception deleted successfully.");
      await renderExceptionList(deps);
      await loadExceptions(deps);
    } catch (error) {
      deps.setStatus(`Error: ${error?.message || "Unknown error"}`, true);
    }
  }

  async function editException(deps, exceptionId) {
    const excelUserEmail = deps.getExcelUserEmail();
    if (!excelUserEmail) {
      deps.setStatus("Could not determine Excel user email.", true);
      return;
    }

    try {
      const response = await fetch(`${deps.CONFIG.BACKEND_URL}/api/v1/exceptions`, {
        method: "GET",
        headers: { "X-Excel-User-Email": excelUserEmail },
        cache: "no-store",
      });

      if (!response.ok) {
        deps.setStatus("Failed to load exception details.", true);
        return;
      }

      const payload = await response.json().catch(() => ({ exceptions: [] }));
      const exceptions = Array.isArray(payload?.exceptions) ? payload.exceptions : [];
      const exception = exceptions.find((e) => e.exception_id === exceptionId);

      if (!exception) {
        deps.setStatus("Exception not found.", true);
        return;
      }

      document.getElementById("exceptionIdInput").value = exception.exception_id;
      await loadLinkedFieldsForExceptionModal(deps);
      document.getElementById("exceptionFieldInput").value = exception.linked_field || exception.test_id || "";
      document.getElementById("exceptionUmrInput").value = exception.linked_umr || "";
      document.getElementById("exceptionDescriptionInput").value = exception.description;
      document.getElementById("exceptionStatusInput").value = exception.status;

      const createBtn = document.getElementById("createExceptionBtn");
      createBtn.textContent = "Update";
      createBtn.title = "Update the selected exception or record.";
      createBtn.dataset.editMode = "true";
      createBtn.dataset.originalExceptionId = exceptionId;

      const formTitle = document.getElementById("exceptionFormTitle");
      if (formTitle) formTitle.textContent = "Edit Exception";

      document.querySelector('input[id="exceptionIdInput"]').focus();
    } catch (error) {
      deps.setStatus(`Error: ${error?.message || "Unknown error"}`, true);
    }
  }

  async function applyExceptionToCell(deps) {
    const exceptionSelect = document.getElementById("exceptionSelect");
    const selectedExceptionId = exceptionSelect?.value?.trim();

    if (!selectedExceptionId) {
      deps.setStatus("Please select an exception to apply.", true);
      return;
    }

    try {
      const selection = await Excel.run(async (context) => {
        const range = context.workbook.getSelectedRange();
        const worksheet = context.workbook.worksheets.getActiveWorksheet();
        range.load("address");
        worksheet.load("name");
        await context.sync();
        return { address: range.address, sheetName: worksheet.name };
      });

      if (!selection?.address) {
        deps.setStatus("Please select at least one cell to apply exception.", true);
        return;
      }

      const workbookName = deps.getWorkbookName() || "__unknown_workbook__";
      const sheetName = String(selection.sheetName || "").trim() || (await deps.getActiveSheetName()) || "__unknown_sheet__";

      const addresses = deps.parseExcelAddress(selection.address);
      if (addresses.length === 0) {
        deps.setStatus("Could not parse selected cell address.", true);
        return;
      }

      const previousFillByAddress = await getCurrentFillColorsForAddresses(deps, addresses);

      const taggedCells = addresses.map((address) => ({
        address,
        exception_id: selectedExceptionId,
        comment: `Exception tagged: ${selectedExceptionId}`,
        fill_color: deps.EXCEPTION_TAG_FILL,
        previous_fill_color: String(previousFillByAddress.get(address) || "").trim(),
        sheet_name: sheetName,
        workbook_name: workbookName,
        tagged_at: new Date().toISOString(),
      }));

      deps.setStatus("Applying exception to selected cells...");
      await deps.applyExceptionTagsToSheet(taggedCells);
      deps.setLastTaggedCells(deps.mergeTaggedCells(deps.getLastTaggedCells(), taggedCells));
      deps.persistValidationResults();
      await deps.syncTaggedCellsToBackend(selectedExceptionId, addresses, sheetName, workbookName, taggedCells);
      deps.setStatus(`Exception '${selectedExceptionId}' applied to ${addresses.length} cell(s).`);
    } catch (error) {
      deps.setStatus(`Error: ${error?.message || "Unknown error"}`, true);
    }
  }

  global.TaskpaneExceptionActions = {
    loadExceptions,
    fetchStoredExceptionsForAutoTagging,
    loadLinkedFieldsForExceptionModal,
    openExceptionModal,
    closeExceptionModal,
    renderExceptionList,
    splitTaggedCellsByException,
    unapplyDeletedExceptionFromWorkbook,
    getCurrentFillColorsForAddresses,
    createException,
    deleteException,
    editException,
    applyExceptionToCell,
  };
}(window));
