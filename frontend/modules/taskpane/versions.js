(function initTaskpaneVersionHelpers(global) {
  function updateSaveButtonLabel(saveButton, savedResultsVersionExists, activeViewedVersionContext) {
    if (!saveButton) {
      return;
    }
    saveButton.textContent = (savedResultsVersionExists || Boolean(activeViewedVersionContext))
      ? "Update Report"
      : "Save Report";
  }

  function renderSavedVersionsDropdown(select, items) {
    if (!select) {
      return [];
    }

    const savedVersionItems = Array.isArray(items) ? items : [];
    select.innerHTML = "";

    if (savedVersionItems.length === 0) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No saved versions";
      select.appendChild(option);
      return savedVersionItems;
    }

    for (const item of savedVersionItems) {
      const option = document.createElement("option");
      option.value = String(item.id || "");
      option.dataset.currentScope = Boolean(item.current_scope || item.currentScope) ? "true" : "false";
      const versionTimestamp = new Date(
        item.updated_at
        || item.updatedAt
        || item.created_at
        || item.createdAt
        || Date.now()
      );
      const customName = String(item.version_name || item.versionName || "").trim();
      option.textContent = customName || `Version ${versionTimestamp.toLocaleString()}`;
      select.appendChild(option);
    }

    select.selectedIndex = 0;
    return savedVersionItems;
  }

  function getSelectedSavedVersionItem(savedVersionItems, selectedVersionId) {
    if (!selectedVersionId) {
      return null;
    }
    return (savedVersionItems || []).find((item) => Number(item?.id || 0) === selectedVersionId) || null;
  }

  function normalizeExcelSheetNameCandidate(rawName, maxSheetNameLength) {
    const limit = Number(maxSheetNameLength) || 31;
    const fallback = "Saved Report";
    const cleaned = String(rawName || "")
      .replace(/[\\/?*\[\]:]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    const candidate = cleaned || fallback;
    return candidate.slice(0, limit);
  }

  async function createUniqueWorksheetName(baseName, maxSheetNameLength) {
    const normalizedBase = normalizeExcelSheetNameCandidate(baseName, maxSheetNameLength);
    const limit = Number(maxSheetNameLength) || 31;

    return Excel.run(async (context) => {
      const worksheets = context.workbook.worksheets;
      worksheets.load("items/name");
      await context.sync();

      const existingNames = new Set((worksheets.items || []).map((sheet) => String(sheet.name || "").trim()));
      if (!existingNames.has(normalizedBase)) {
        return normalizedBase;
      }

      let suffixIndex = 2;
      while (suffixIndex < 1000) {
        const suffix = ` (${suffixIndex})`;
        const candidate = `${normalizedBase.slice(0, Math.max(1, limit - suffix.length))}${suffix}`;
        if (!existingNames.has(candidate)) {
          return candidate;
        }
        suffixIndex += 1;
      }

      return `${normalizedBase.slice(0, 26)} (${Date.now() % 1000})`;
    });
  }

  function toExcelCellValue(value) {
    if (value === null || value === undefined) {
      return "";
    }
    if (typeof value === "number" || typeof value === "boolean" || typeof value === "string") {
      return value;
    }
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }

  function deriveSavedReportHeaders(savedData, mappedHeaders) {
    const headerSet = new Set();

    if (Array.isArray(savedData)) {
      for (const row of savedData) {
        if (!row || typeof row !== "object" || Array.isArray(row)) {
          continue;
        }
        for (const key of Object.keys(row)) {
          const normalized = String(key || "").trim();
          if (normalized) {
            headerSet.add(normalized);
          }
        }
      }
    }

    if (headerSet.size === 0 && mappedHeaders && typeof mappedHeaders === "object" && !Array.isArray(mappedHeaders)) {
      for (const [key, value] of Object.entries(mappedHeaders)) {
        const mapped = String(value || "").trim();
        const source = String(key || "").trim();
        if (mapped) {
          headerSet.add(mapped);
        } else if (source) {
          headerSet.add(source);
        }
      }
    }

    return Array.from(headerSet);
  }

  async function launchSavedReportSheet({ versionName, savedData, mappedHeaders, maxSheetNameLength, appendDebugLog }) {
    const sheetName = await createUniqueWorksheetName(versionName, maxSheetNameLength);
    const dataRows = Array.isArray(savedData) ? savedData : [];
    const headers = deriveSavedReportHeaders(dataRows, mappedHeaders);

    if (typeof appendDebugLog === "function") {
      appendDebugLog("Launching saved report sheet", {
        sheetName,
        rows: dataRows.length,
        columns: headers.length,
      });
    }

    if (headers.length === 0) {
      throw new Error("Saved report has no tabular data to launch.");
    }

    await Excel.run(async (context) => {
      const worksheet = context.workbook.worksheets.add(sheetName);
      const colCount = Math.max(1, headers.length);

      const headerRowRange = worksheet.getRangeByIndexes(0, 0, 1, colCount);
      headerRowRange.values = [headers];
      await context.sync();

      const WRITE_BATCH_SIZE = 1000;
      for (let start = 0; start < dataRows.length; start += WRITE_BATCH_SIZE) {
        const batchRows = dataRows.slice(start, start + WRITE_BATCH_SIZE);
        const normalizedBatch = batchRows.map((row) => headers.map((header) => toExcelCellValue(
          row && typeof row === "object" && !Array.isArray(row) ? row[header] : ""
        )));
        const dataRange = worksheet.getRangeByIndexes(1 + start, 0, normalizedBatch.length, colCount);
        dataRange.values = normalizedBatch;
        await context.sync();
        if (typeof appendDebugLog === "function") {
          appendDebugLog("Saved report write batch complete", {
            sheetName,
            start,
            count: normalizedBatch.length,
          });
        }
      }

      const headerRange = worksheet.getRangeByIndexes(0, 0, 1, colCount);
      headerRange.format.font.bold = true;
      headerRange.format.fill.color = "#ffffff";
      headerRange.format.font.color = "#000000";

      const usedRange = worksheet.getUsedRangeOrNullObject();
      usedRange.load("isNullObject");
      await context.sync();
      if (!usedRange.isNullObject) {
        usedRange.format.autofitColumns();
      }
      worksheet.activate();
      await context.sync();
    });

    return sheetName;
  }

  function computeCurrentScopeVersionState(versions) {
    const currentScopeVersion = (versions || []).find(
      (item) => Boolean(item?.current_scope || item?.currentScope)
    );
    const exists = Boolean(currentScopeVersion);
    const createdAt = exists
      ? String(
          currentScopeVersion?.updated_at
          || currentScopeVersion?.updatedAt
          || currentScopeVersion?.created_at
          || currentScopeVersion?.createdAt
          || ""
        ).trim() || null
      : null;
    return { exists, createdAt };
  }

  global.TaskpaneVersions = {
    updateSaveButtonLabel,
    renderSavedVersionsDropdown,
    getSelectedSavedVersionItem,
    normalizeExcelSheetNameCandidate,
    createUniqueWorksheetName,
    toExcelCellValue,
    deriveSavedReportHeaders,
    launchSavedReportSheet,
    computeCurrentScopeVersionState,
  };
}(window));
