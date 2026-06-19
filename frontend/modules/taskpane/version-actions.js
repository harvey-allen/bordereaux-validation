(function initTaskpaneVersionActions(global) {
  async function checkSavedResultsVersion(deps) {
    const excelUserEmail = deps.getExcelUserEmail();
    if (!excelUserEmail) {
      deps.setSavedResultsVersionState(false, null);
      deps.renderSavedVersionsDropdown([]);
      deps.updateSavedResultsInfo();
      deps.updateActionButtons();
      return;
    }

    const { workbookName, sheetName } = await deps.getCurrentResultsScope();
    const selectedPack = deps.getSelectedPack();
    if (!selectedPack) {
      deps.setSavedResultsVersionState(false, null);
      deps.renderSavedVersionsDropdown([]);
      deps.updateSavedResultsInfo();
      deps.updateActionButtons();
      return;
    }

    const query = new URLSearchParams({ workbook_name: workbookName, sheet_name: sheetName, test_pack: selectedPack });

    try {
      const response = await fetch(`${deps.CONFIG.BACKEND_URL}/api/v1/results/versions?${query.toString()}`, {
        method: "GET",
        headers: { "X-Excel-User-Email": excelUserEmail },
        cache: "no-store",
      });

      if (!response.ok) {
        deps.setSavedResultsVersionState(false, null);
        deps.renderSavedVersionsDropdown([]);
        deps.updateSavedResultsInfo();
        deps.updateActionButtons();
        return;
      }

      const payload = await response.json().catch(() => ({}));
      const versions = Array.isArray(payload?.versions) ? payload.versions : [];
      deps.renderSavedVersionsDropdown(versions);
      const state = deps.versionHelpers.computeCurrentScopeVersionState(versions);
      deps.setSavedResultsVersionState(Boolean(state?.exists), String(state?.createdAt || "").trim() || null);
      deps.updateSavedResultsInfo();
      deps.updateActionButtons();
    } catch {
      deps.setSavedResultsVersionState(false, null);
      deps.renderSavedVersionsDropdown([]);
      deps.updateSavedResultsInfo();
      deps.updateActionButtons();
    }
  }

  async function refreshVersionStateForActiveSheet(deps) {
    await deps.refreshActiveViewedVersionContext();
    await checkSavedResultsVersion(deps);
    deps.updateSaveButtonLabel();
    deps.updateActionButtons();
  }

  async function viewSelectedSavedVersion(deps) {
    const button = document.getElementById("viewSavedVersion");
    const selectedVersion = deps.getSelectedSavedVersionItem();

    if (!selectedVersion) {
      deps.setStatus("Select a saved version to view.", true);
      return;
    }

    if (Boolean(selectedVersion.current_scope || selectedVersion.currentScope)) {
      deps.setStatus("The selected saved version is already for the active sheet.", true);
      deps.updateActionButtons();
      return;
    }

    const excelUserEmail = deps.getExcelUserEmail();
    if (!excelUserEmail) {
      deps.setStatus("Could not determine Excel user email.", true);
      return;
    }

    if (button) button.disabled = true;

    try {
      deps.appendDebugLog("View saved version clicked", {
        versionId: Number(selectedVersion.id),
        currentScope: Boolean(selectedVersion.current_scope || selectedVersion.currentScope),
      });

      const response = await fetch(`${deps.CONFIG.BACKEND_URL}/api/v1/results/versions/${Number(selectedVersion.id)}`, {
        method: "GET",
        headers: { "X-Excel-User-Email": excelUserEmail },
        cache: "no-store",
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const detail = deps.formatBackendErrorDetail(errorData?.detail) || `HTTP ${response.status}`;
        throw new Error(detail);
      }

      const payload = await response.json().catch(() => ({}));
      deps.appendDebugLog("Fetched saved version payload", {
        versionId: Number(selectedVersion.id),
        testPack: payload?.test_pack,
        savedDataRows: Array.isArray(payload?.saved_data) ? payload.saved_data.length : 0,
        mappedHeaderCount: payload?.mapped_headers && typeof payload.mapped_headers === "object"
          ? Object.keys(payload.mapped_headers).length : 0,
      });

      const versionName = String(
        payload?.version_name || payload?.versionName
        || selectedVersion?.version_name || selectedVersion?.versionName
        || "Saved Report"
      ).trim();

      deps.setStatus("Launching saved report in a new worksheet...");
      const launchedSheetName = await deps.launchSavedReportSheet({
        versionName,
        savedData: payload?.saved_data,
        mappedHeaders: payload?.mapped_headers,
      });

      const normalizedConfig = await deps.applySavedVersionPackConfiguration(payload?.test_pack, payload?.pack_config);
      await deps.persistPackConfigurationForSheet(payload?.test_pack, normalizedConfig, launchedSheetName);
      deps.setViewedVersionContextForSheet({
        workbookName: deps.getWorkbookName() || "__unknown_workbook__",
        sheetName: launchedSheetName,
        versionId: Number(payload?.id || selectedVersion?.id || 0),
        sheetKeyId: Number(payload?.sheet_key_id || 0),
        testPack: payload?.test_pack,
        versionName,
      });
      await deps.refreshActiveViewedVersionContext();
      deps.appendDebugLog("Saved version config restored and persisted", {
        versionId: Number(selectedVersion.id),
        launchedSheetName,
        testPack: payload?.test_pack,
      });
      await refreshVersionStateForActiveSheet(deps);

      deps.setStatus(`Saved report launched in '${launchedSheetName}'. Running validation...`);
      await deps.runValidation();
      deps.appendDebugLog("Validation run completed for launched saved version", {
        launchedSheetName,
        versionId: Number(selectedVersion.id),
      });
    } catch (error) {
      deps.appendDebugLog("View saved version failed", {
        message: String(error?.message || "Unexpected error"),
        stack: String(error?.stack || ""),
      });
      deps.setStatus(`View failed: ${error?.message || "Unexpected error"}`, true);
    } finally {
      if (button) button.disabled = false;
      deps.updateActionButtons();
    }
  }

  async function saveResultsVersion(deps) {
    const saveButton = document.getElementById("saveResultsVersion");
    if (!Array.isArray(deps.getLastValidationResults()) || deps.getLastValidationResults().length === 0) {
      deps.setStatus("No validation results to save. Please run validation first.", true);
      return;
    }

    const excelUserEmail = deps.getExcelUserEmail();
    if (!excelUserEmail) {
      deps.setStatus("Could not determine Excel user email.", true);
      return;
    }

    if (saveButton) saveButton.disabled = true;

    try {
      const activeSheetName = await deps.getActiveSheetName();
      const lastValidationSourceSheetName = deps.getLastValidationSourceSheetName();
      if (activeSheetName && lastValidationSourceSheetName && activeSheetName !== lastValidationSourceSheetName) {
        deps.setStatus("Please run validation on the active sheet before saving a version.", true);
        return;
      }

      const { workbookName, sheetName } = await deps.getCurrentResultsScope({ preferValidationSheet: true });
      const selectedPack = deps.getSelectedPack();
      if (!selectedPack) throw new Error("Select a test pack before saving.");

      await checkSavedResultsVersion(deps);
      const viewedVersionContext = deps.getViewedVersionContextForSheet(workbookName, sheetName);
      const isViewedVersionUpdate = Boolean(viewedVersionContext && Number(viewedVersionContext.versionId || 0));
      const { exists: savedResultsVersionExists } = deps.getSavedResultsVersionState();
      const isUpdate = savedResultsVersionExists || isViewedVersionUpdate;

      const savedVersionItems = deps.getSavedVersionItems();
      const selectedVersionId = Number(document.getElementById("savedVersions")?.value || 0);
      const selectedVersion = savedVersionItems.find((item) => Number(item?.id || 0) === selectedVersionId) || (savedVersionItems[0] || null);
      const fallbackTimestamp = new Date(
        selectedVersion?.updated_at || selectedVersion?.updatedAt
        || selectedVersion?.created_at || selectedVersion?.createdAt || Date.now()
      ).toLocaleString();
      const suggestedName = String(
        viewedVersionContext?.versionName || selectedVersion?.version_name || selectedVersion?.versionName || ""
      ).trim() || `Report ${fallbackTimestamp}`;

      const requestedName = await deps.promptForReportName(suggestedName);
      if (requestedName === null) { deps.setStatus("Save cancelled."); return; }

      const versionName = String(requestedName || "").trim();
      if (!versionName) { deps.setStatus("Save failed: report name cannot be blank.", true); return; }

      const failedTests = Array.isArray(deps.getLastValidationFailedTests())
        ? deps.getLastValidationFailedTests()
            .map((item) => ({ id: String(item?.id || item?.umr || ""), umr: String(item?.umr || ""), test_id: String(item?.test_id || "") }))
            .filter((item) => item.test_id)
        : [];
      const passedTests = Array.isArray(deps.getLastValidationPassedTests())
        ? deps.getLastValidationPassedTests().map((item) => String(item || "").trim()).filter(Boolean)
        : [];
      const passedUmrs = Array.isArray(deps.getLastValidationPassedUmrs())
        ? deps.getLastValidationPassedUmrs().map((item) => String(item || "").trim()).filter(Boolean)
        : [];

      const currentPackConfig = deps.getPackConfigsByPack()[selectedPack] || {};
      const mappedHeaders = currentPackConfig.fieldMappings || currentPackConfig.FieldMappings || currentPackConfig.columnMappings || {};

      const savedData = await deps.buildCurrentSheetDataPayload();
      const taggedCells = deps.getTaggedCellsForScope(workbookName, sheetName);
      const exportRows = await deps.buildFailureExportRows();
      const computedKpis = await deps.computeVisualisationKpisFromCurrentRun(exportRows);
      const kpisForSave = {
        submissions_failed: computedKpis.submissions_failed,
        submissions_failed_pct: computedKpis.submissions_failed_pct,
        fields_failed: computedKpis.fields_failed,
        fields_failed_pct: computedKpis.fields_failed_pct,
        tests_failed: computedKpis.tests_failed,
        tests_failed_pct: computedKpis.tests_failed_pct,
        tests_passed_pct: computedKpis.tests_passed_pct,
        total_submissions: computedKpis.total_submissions,
        total_fields: computedKpis.total_fields,
        total_tests: computedKpis.total_tests,
        computed_at: computedKpis.computed_at,
      };

      const requestUrl = isViewedVersionUpdate
        ? `${deps.CONFIG.BACKEND_URL}/api/v1/results/versions/${Number(viewedVersionContext.versionId)}`
        : `${deps.CONFIG.BACKEND_URL}/api/v1/results/versions`;
      const requestMethod = isViewedVersionUpdate ? "PUT" : "POST";

      if (isViewedVersionUpdate) {
        const expectedPack = String(viewedVersionContext?.testPack || "").trim().toLowerCase();
        if (expectedPack && expectedPack !== selectedPack) {
          throw new Error(`This viewed report is linked to '${expectedPack}'. Switch back to that pack to update it.`);
        }
      }

      const response = await fetch(requestUrl, {
        method: requestMethod,
        headers: { "Content-Type": "application/json", "X-Excel-User-Email": excelUserEmail },
        body: JSON.stringify({
          workbook_name: workbookName,
          sheet_name: sheetName,
          test_pack: selectedPack,
          failed_tests: failedTests,
          passed_tests: passedTests,
          passed_umrs: passedUmrs,
          mapped_headers: mappedHeaders,
          saved_data: savedData,
          tagged_cells: taggedCells,
          version_name: versionName,
          kpis: kpisForSave,
          summary_metrics: kpisForSave,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const detail = deps.formatBackendErrorDetail(errorData?.detail) || `HTTP ${response.status}`;
        throw new Error(detail);
      }

      await checkSavedResultsVersion(deps);
      if (isViewedVersionUpdate) {
        deps.appendDebugLog("Updated viewed saved version", {
          versionId: Number(viewedVersionContext.versionId),
          workbookName,
          sheetName,
          selectedPack,
        });
        deps.setStatus(`Updated viewed report version ${Number(viewedVersionContext.versionId)}.`);
      } else {
        deps.setStatus(isUpdate ? "Updated current results version." : "Saved current results version.");
      }
    } catch (error) {
      deps.setStatus(`Save failed: ${error?.message || "Unexpected error"}`, true);
    } finally {
      if (saveButton) saveButton.disabled = false;
      deps.updateActionButtons();
    }
  }

  async function deleteSelectedResultsVersion(deps) {
    const deleteButton = document.getElementById("deleteResultsVersion");
    const select = document.getElementById("savedVersions");
    const selectedVersionId = Number(select?.value || 0);

    if (!selectedVersionId) {
      deps.setStatus("Select a saved version to delete.", true);
      return;
    }

    const excelUserEmail = deps.getExcelUserEmail();
    if (!excelUserEmail) {
      deps.setStatus("Could not determine Excel user email.", true);
      return;
    }

    if (deleteButton) deleteButton.disabled = true;

    try {
      const response = await fetch(`${deps.CONFIG.BACKEND_URL}/api/v1/results/versions/${selectedVersionId}`, {
        method: "DELETE",
        headers: { "X-Excel-User-Email": excelUserEmail },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const detail = deps.formatBackendErrorDetail(errorData?.detail) || `HTTP ${response.status}`;
        throw new Error(detail);
      }

      deps.removeViewedVersionContextByVersionId(selectedVersionId);
      await deps.refreshActiveViewedVersionContext();
      await checkSavedResultsVersion(deps);
      deps.setStatus(`Deleted saved version ${selectedVersionId}.`);
    } catch (error) {
      deps.setStatus(`Delete failed: ${error?.message || "Unexpected error"}`, true);
    } finally {
      if (deleteButton) deleteButton.disabled = false;
      deps.updateActionButtons();
    }
  }

  global.TaskpaneVersionActions = {
    viewSelectedSavedVersion,
    refreshVersionStateForActiveSheet,
    checkSavedResultsVersion,
    saveResultsVersion,
    deleteSelectedResultsVersion,
  };
}(window));
