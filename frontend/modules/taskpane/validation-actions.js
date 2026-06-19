(function initTaskpaneValidationActions(global) {
  function normalizeForComparison(value) {
    return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]/g, "");
  }

  async function generateTemplate(deps) {
    const button = document.getElementById("generateTemplate");
    const backendUrl = deps.CONFIG.BACKEND_URL;
    const excelUserEmail = deps.getExcelUserEmail();
    let generatedSheetName = null;

    if (!button) return;

    try {
      button.disabled = true;
      deps.setStatus("Generating template...");

      const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
      const selectedTerritory = String(document.getElementById("territory")?.value || "").trim();

      if (!selectedPack) {
        throw new Error("Please select a test pack first");
      }

      if (!selectedTerritory) {
        throw new Error("Please select a territory first");
      }

      const response = await fetch(
        `${backendUrl}/api/v1/generate-template?test_pack=${encodeURIComponent(selectedPack)}&territory=${encodeURIComponent(selectedTerritory)}`,
        {
          method: "GET",
          headers: {
            "X-Excel-User-Email": excelUserEmail,
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const templateData = await response.json();
      let headers = templateData.headers || [];

      if (headers.length === 0) {
        throw new Error("No fields available for this pack and territory");
      }

      const currentPackConfig = deps.getPackConfigsByPack()[selectedPack];
      const aliases = currentPackConfig?.aliases || {};

      headers = headers.map((header) => {
        for (const [aliasKey, aliasValue] of Object.entries(aliases)) {
          if (aliasValue === header) {
            return aliasKey;
          }
        }
        return header;
      });

      await Excel.run(async (context) => {
        const workbook = context.workbook;
        const sheets = workbook.worksheets;

        generatedSheetName = `${deps.formatPackLabel(selectedPack)} - ${selectedTerritory}`.substring(0, 31);
        const newSheet = sheets.add(generatedSheetName);

        const lastCol = deps.columnToA1(headers.length - 1);
        const headerRangeAddress = `A1:${lastCol}1`;

        const headerRange = newSheet.getRange(headerRangeAddress);
        headerRange.values = [headers];

        headerRange.format.font.bold = true;
        headerRange.format.fill.color = "#ffffff";
        headerRange.format.font.color = "#000000";
        headerRange.format.autofitColumns();

        newSheet.activate();

        await context.sync();
      });

      deps.setStatus(`Template generated with ${headers.length} fields in new sheet: ${generatedSheetName}`);

      try {
        await deps.persistPackConfigStateForScope({
          scope: deps.getCurrentSheetPackConfigScope(),
          persistToServer: true,
          showValidationError: false,
        });
      } catch (error) {
        deps.reportFrontendError("Could not save configuration before sheet switch", error, { showStatus: false });
      }

      await new Promise((resolve) => setTimeout(resolve, 250));

      const configTab = document.getElementById("tabConfiguration");
      if (configTab) {
        configTab.click();
      }

      try {
        if (typeof Office?.addin?.show === "function") {
          await Office.addin.show();
        }
      } catch {
        // Best effort only
      }
    } catch (error) {
      deps.setStatus(`Template generation failed: ${error?.message || "Unexpected error"}`, true);
    } finally {
      if (button) {
        button.disabled = false;
      }
    }
  }

  async function estimateFieldMapping(deps) {
    const button = document.getElementById("estimateFieldMapping");
    const excelUserEmail = deps.getExcelUserEmail();

    if (!button) return;

    try {
      button.disabled = true;
      deps.setStatus("Extracting headers and estimating field mapping...");

      const selectedPack = String(document.getElementById("testPacks")?.value || "").trim().toLowerCase();
      const selectedTerritory = deps.getSelectedTerritoryValue();

      if (!selectedPack) {
        throw new Error("Please select a test pack first");
      }

      if (!selectedTerritory) {
        throw new Error("Please select a territory first");
      }

      const sheetContext = await deps.resolveValidationRangeMeta();
      if (!sheetContext) {
        throw new Error("Could not extract headers from active sheet");
      }

      const headerValues = sheetContext.headerValues || [];
      if (headerValues.length === 0) {
        throw new Error("No headers found on the active sheet");
      }

      const normalizedHeaders = headerValues.map((h) => String(h || "").trim()).filter(Boolean);
      if (normalizedHeaders.length === 0) {
        throw new Error("No non-empty headers found on the active sheet");
      }

      const estimateFieldMappingApi = deps.estimateFieldMappingApi;
      if (!estimateFieldMappingApi) {
        throw new Error("Field mapping estimation service not available");
      }

      const estimationResult = await estimateFieldMappingApi(excelUserEmail, selectedPack, selectedTerritory, normalizedHeaders);

      if (!estimationResult) {
        throw new Error("No estimation result returned from server");
      }

      await mergeEstimationIntoParkConfig(deps, selectedPack, estimationResult);

      deps.setStatus(
        `Field mapping estimated: ${estimationResult.matched_count || 0} matched, ${estimationResult.unmatched_count || 0} unmatched`,
        false
      );
    } catch (error) {
      let errorMessage = "Unexpected error";
      if (error instanceof Error) {
        errorMessage = error.message;
      } else if (typeof error === "string") {
        errorMessage = error;
      } else if (error && typeof error === "object") {
        errorMessage = error.detail || error.message || String(error);
      }
      deps.setStatus(`Field mapping estimation failed: ${errorMessage}`, true);
    } finally {
      if (button) {
        button.disabled = false;
      }
    }
  }

  async function mergeEstimationIntoParkConfig(deps, testPack, estimationResult) {
    const normalizedPack = String(testPack || "").trim().toLowerCase();
    if (!normalizedPack) {
      return;
    }

    const packConfigEditor = document.getElementById("packConfigs");
    if (!packConfigEditor) {
      return;
    }

    let currentConfig;
    try {
      currentConfig = deps.parsePackConfigInput(packConfigEditor.value, normalizedPack);
    } catch {
      currentConfig = deps.getDefaultPackConfig(normalizedPack);
    }

    const estimatedAliases = estimationResult.estimated_mappings || {};
    const filteredEstimates = {};
    for (const [header, schemaField] of Object.entries(estimatedAliases)) {
      const normalizedHeader = normalizeForComparison(header);
      const normalizedField = normalizeForComparison(schemaField);

      if (normalizedHeader !== normalizedField) {
        filteredEstimates[header] = schemaField;
      }
    }

    const mergedAliases = {
      ...filteredEstimates,
      ...(currentConfig.aliases || {}),
    };

    const updatedConfig = {
      ...currentConfig,
      aliases: mergedAliases,
    };

    packConfigEditor.value = JSON.stringify(updatedConfig, null, 2);
    packConfigEditor.dispatchEvent(new Event("input", { bubbles: true }));
    deps.schedulePackConfigStatePersist({ delayMs: 0, persistToServer: true, showValidationError: true, showSaveError: true });
  }

  async function runValidation(deps) {
    const button = document.getElementById("runValidation");
    const clearButton = document.getElementById("clearTable");
    const backendUrl = deps.CONFIG.BACKEND_URL;
    const maxCellsPerChunk = deps.CONFIG.MAX_CELLS_PER_CHUNK;

    const selectedPack = String(document.getElementById("testPacks").value || "").trim().toLowerCase();
    const testPacks = [selectedPack];
    const packConfigEditor = document.getElementById("packConfigs");
    let selectedPackConfig;
    try {
      selectedPackConfig = deps.parsePackConfigInput(packConfigEditor.value, selectedPack);
    } catch {
      deps.setStatus("Pack configs JSON is invalid.", true);
      return;
    }

    const normalizedConfig = deps.withDefaultEnabledTests(
      { [selectedPack]: selectedPackConfig },
      selectedPack
    )[selectedPack];
    const selectedTerritory = deps.getSelectedTerritoryValue();
    if (selectedTerritory) {
      normalizedConfig.territory = selectedTerritory;
    } else {
      delete normalizedConfig.territory;
    }
    deps.setPackConfigForPack(selectedPack, normalizedConfig);
    deps.setCurrentPackSelection(selectedPack);
    packConfigEditor.value = JSON.stringify(normalizedConfig, null, 2);
    const packConfigs = { [selectedPack]: normalizedConfig };

    await deps.persistPackConfigStateForScope({ persistToServer: true, showValidationError: true });

    const excelUserEmail = deps.getExcelUserEmail();
    if (!excelUserEmail) {
      deps.setStatus("Validation failed: Could not determine Excel user email.", true);
      return;
    }

    button.disabled = true;
    deps.setStatus("Detecting table on active sheet...");

    try {
      const selectionMeta = await deps.resolveValidationRangeMeta();
      deps.setLastValidationSourceSheetName(selectionMeta.sheetName || null);
      deps.setLastValidationExecutedTests([]);
      deps.setLastValidationResults([]);
      deps.setLastValidationFailedTests([]);
      deps.setLastValidationPassedTests([]);
      deps.setLastValidationPack(selectedPack);
      deps.clearPersistedValidationResultsForScope({
        workbookName: deps.getWorkbookName() || "__unknown_workbook__",
        sheetName: selectionMeta.sheetName || "__unknown_sheet__",
      });

      if (clearButton) {
        clearButton.disabled = true;
      }

      const dataRowCount = selectionMeta.rowCount - 1;
      const rowsPerChunk = Math.max(1, Math.floor(maxCellsPerChunk / selectionMeta.columnCount));
      const totalChunks = Math.ceil(dataRowCount / rowsPerChunk);

      const targetDescription = selectionMeta.source === "selection" ? "selected range" : "detected table";
      deps.setStatus(`Clearing existing comments in ${targetDescription}...`);
      await deps.clearCommentsInRange(
        selectionMeta.startRow,
        selectionMeta.startCol,
        selectionMeta.rowCount,
        selectionMeta.columnCount
      );

      let failedCount = 0;
      const aggregatedResults = [];
      const executedTestNames = new Set();
      const executedTestIds = new Set();
      const failedTestIds = new Set();
      const failedEntryByKey = new Map();
      const umrsInData = new Set();
      const failedUmrs = new Set();
      const coverageWarnings = new Set();
      const referenceColumnIndex = deps.resolveReferenceColumnIndex(selectionMeta.headerValues, selectedPack);
      const workbookNameForScope = deps.getWorkbookName() || "__unknown_workbook__";
      const sheetNameForScope = selectionMeta.sheetName || "__unknown_sheet__";

      const storedExceptions = await deps.fetchStoredExceptionsForAutoTagging(excelUserEmail);
      const exceptionLookup = deps.buildLinkedExceptionLookup(storedExceptions);

      const alreadyTaggedAddresses = new Set();
      for (const rawItem of deps.getTaggedCellsForScope(workbookNameForScope, sheetNameForScope)) {
        const taggedCell = deps.normalizeTaggedCellRecord(rawItem);
        if (!taggedCell) {
          continue;
        }
        alreadyTaggedAddresses.add(String(taggedCell.address || "").replace(/\$/g, "").trim().toUpperCase());
      }

      const autoTaggedCellByAddress = new Map();

      for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
        const chunkDataStartOffset = chunkIndex * rowsPerChunk;
        const currentDataRows = Math.min(rowsPerChunk, dataRowCount - chunkDataStartOffset);
        const chunkStartRow = selectionMeta.startRow + 1 + chunkDataStartOffset;

        deps.setStatus(`Validating chunk ${chunkIndex + 1}/${totalChunks}...`);
        const chunkValues = await deps.readRangeValues(
          chunkStartRow,
          selectionMeta.startCol,
          currentDataRows,
          selectionMeta.columnCount
        );

        const chunkAddresses = [];
        for (let rowOffset = 0; rowOffset < currentDataRows; rowOffset += 1) {
          chunkAddresses.push(
            deps.buildAddressRow(chunkStartRow + rowOffset, selectionMeta.startCol, selectionMeta.columnCount)
          );
        }

        const payloadAddresses = [selectionMeta.headerAddresses, ...chunkAddresses];
        const payloadValues = [selectionMeta.headerValues, ...chunkValues];
        const workbookName = deps.getWorkbookName();

        const response = await fetch(`${backendUrl}/validate-range`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Excel-User-Email": excelUserEmail,
          },
          body: JSON.stringify({
            addresses: payloadAddresses,
            values: payloadValues,
            testPacks,
            hasHeaderRow: true,
            packConfigs,
            includeCoverage: true,
            workbookName,
            sheetName: selectionMeta.sheetName || null,
          }),
        });

        if (!response.ok) {
          const errorText = await response.text().catch(() => "");
          let errorData = {};
          if (errorText) {
            try {
              errorData = JSON.parse(errorText);
            } catch {
              errorData = { detail: errorText };
            }
          }

          const detail = deps.formatBackendErrorDetail(errorData.detail) || `HTTP ${response.status}`;
          throw new Error(detail);
        }

        const data = await response.json();
        const results = data.results || [];
        aggregatedResults.push(...results);
        const maxSeverityScore = Math.max(
          ...results.map((result) => result.severityScore !== undefined ? result.severityScore : result.failCount || 0),
          1
        );

        const coveragePacks = data?.coverage?.packs || {};
        for (const [packName, packCoverage] of Object.entries(coveragePacks)) {
          if (packCoverage?.warning) {
            coverageWarnings.add(`${packName}: ${packCoverage.warning}`);
          }
          if (Array.isArray(packCoverage?.warnings)) {
            for (const warning of packCoverage.warnings) {
              coverageWarnings.add(`${packName}: ${warning}`);
            }
          }
          const tests = packCoverage?.tests || {};
          for (const [testName, testData] of Object.entries(tests)) {
            executedTestNames.add(`${packName}.${testName}`);
            const testId = String(testData?.testCode || `${packName}.${testName}`).trim();
            if (testId) {
              executedTestIds.add(testId);
              if (Number(testData?.failedRows || 0) > 0) {
                failedTestIds.add(testId);
              }
            }
          }
        }

        for (const result of results) {
          if (!(Number(result?.rowIndex) > 0 && Number(result?.failCount) > 0)) {
            continue;
          }

          const localRowIndex = Number(result.rowIndex) - 1;
          const failedMessages = Array.isArray(result.failedTests) ? result.failedTests : [];
          const rowValues = localRowIndex >= 0 ? chunkValues[localRowIndex] : null;
          const umrValue = (
            referenceColumnIndex >= 0 && Array.isArray(rowValues)
              ? String(rowValues[referenceColumnIndex] ?? "").trim()
              : ""
          );

          if (umrValue) {
            umrsInData.add(umrValue);
            failedUmrs.add(umrValue);
          }

          const fieldName = String(selectionMeta.headerValues?.[Number(result?.columnIndex)] || "").trim();
          const exceptionLookupKey = `${deps.normalizeExceptionMatchValue(umrValue)}::${deps.normalizeExceptionMatchValue(fieldName)}`;
          const matchedException = exceptionLookup.get(exceptionLookupKey);
          const normalizedResultAddress = String(result?.address || "")
            .split("!")
            .pop()
            .replace(/\$/g, "")
            .trim()
            .toUpperCase();

          if (
            matchedException
            && normalizedResultAddress
            && !alreadyTaggedAddresses.has(normalizedResultAddress)
            && !autoTaggedCellByAddress.has(normalizedResultAddress)
          ) {
            autoTaggedCellByAddress.set(normalizedResultAddress, {
              address: normalizedResultAddress,
              exception_id: matchedException.exception_id,
              comment: `Exception tagged: ${matchedException.exception_id}`,
              fill_color: deps.EXCEPTION_TAG_FILL,
              previous_fill_color: "",
              sheet_name: sheetNameForScope,
              workbook_name: workbookNameForScope,
              tagged_at: new Date().toISOString(),
            });
          }

          for (const failedMessage of failedMessages) {
            const testId = deps.extractTestIdFromFailureMessage(failedMessage);
            if (!testId) {
              continue;
            }
            failedTestIds.add(testId);
            const dedupeKey = `${umrValue}::${testId}`;
            if (!failedEntryByKey.has(dedupeKey)) {
              failedEntryByKey.set(dedupeKey, {
                umr: umrValue,
                id: umrValue,
                test_id: testId,
              });
            }
          }
        }

        deps.setStatus(`Applying results for chunk ${chunkIndex + 1}/${totalChunks}...`);
        await deps.applyResultsToSheet(results, maxSeverityScore);

        failedCount += results.filter((item) => item.rowIndex > 0 && item.failCount > 0).length;
      }

      let autoTaggedCount = 0;
      if (autoTaggedCellByAddress.size > 0) {
        const autoTaggedCells = Array.from(autoTaggedCellByAddress.values());
        const fillByAddress = await deps.getCurrentFillColorsForAddresses(autoTaggedCells.map((item) => item.address));
        const tagsWithPreviousFill = autoTaggedCells.map((item) => ({
          ...item,
          previous_fill_color: String(fillByAddress.get(item.address) || item.previous_fill_color || "").trim(),
        }));

        await deps.applyExceptionTagsToSheet(tagsWithPreviousFill);
        deps.setLastTaggedCells(deps.mergeTaggedCells(deps.getLastTaggedCells(), tagsWithPreviousFill));
        deps.persistValidationResults();

        const tagsByException = new Map();
        for (const taggedCell of tagsWithPreviousFill) {
          const exceptionId = String(taggedCell.exception_id || "").trim();
          if (!exceptionId) {
            continue;
          }
          if (!tagsByException.has(exceptionId)) {
            tagsByException.set(exceptionId, []);
          }
          tagsByException.get(exceptionId).push(taggedCell);
        }

        for (const [exceptionId, taggedCells] of tagsByException.entries()) {
          const addresses = taggedCells.map((item) => item.address);
          await deps.syncTaggedCellsToBackend(
            exceptionId,
            addresses,
            sheetNameForScope,
            workbookNameForScope,
            taggedCells
          );
        }

        autoTaggedCount = tagsWithPreviousFill.length;
      }

      const packName = testPacks[0];
      deps.setLastValidationResults(aggregatedResults);
      deps.setLastValidationExecutedTests(Array.from(executedTestNames).sort());
      deps.setLastValidationFailedTests(Array.from(failedEntryByKey.values()));
      deps.setLastValidationPassedTests(Array.from(executedTestIds).filter((testId) => !failedTestIds.has(testId)).sort());
      deps.setLastValidationPassedUmrs(Array.from(umrsInData).filter((umr) => !failedUmrs.has(umr)).sort());
      await deps.reapplyTaggedCellsForScope(workbookNameForScope, sheetNameForScope);
      deps.persistValidationResults();
      await deps.checkSavedResultsVersion();
      const warningText = Array.from(coverageWarnings).join(" | ");
      const statusMessage = `Validation complete with ${packName}: ${failedCount} cells failed at least one test.`;
      const autoTagStatus = autoTaggedCount > 0
        ? ` Auto-tagged ${autoTaggedCount} cell(s) from linked exceptions.`
        : "";
      deps.setStatus(
        warningText ? `${statusMessage}${autoTagStatus} Warning: ${warningText}.` : `${statusMessage}${autoTagStatus}`,
        Boolean(warningText)
      );
    } catch (error) {
      const message = error?.message || "Unexpected error";

      if (/Failed to fetch/i.test(message)) {
        const diagnostic = await deps.getDevelopmentFetchDiagnostics(backendUrl);
        deps.setStatus(`Validation failed: ${message}. ${diagnostic}`, true);
      } else {
        deps.setStatus(`Validation failed: ${message}`, true);
      }
    } finally {
      button.disabled = false;
      if (clearButton) {
        clearButton.disabled = false;
      }
      try { deps.updateActionButtons(); } catch { /* ignore */ }
    }
  }

  global.TaskpaneValidationActions = {
    generateTemplate,
    estimateFieldMapping,
    mergeEstimationIntoParkConfig,
    runValidation,
  };
}(window));
