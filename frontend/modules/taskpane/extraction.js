(function initTaskpaneExtraction(global) {
  async function extractValidationResults(deps) {
    const {
      ensureValidationResultsLoadedForActiveSheet,
      buildFailureExportRows,
      setStatus,
      getLastValidationResults,
    } = deps;

    const extractButton = document.getElementById("extractResults");

    await ensureValidationResultsLoadedForActiveSheet();
    
    const lastValidationResults = getLastValidationResults();
    if (!lastValidationResults || lastValidationResults.length === 0) {
      setStatus("No validation results to extract. Please run validation first.", true);
      return;
    }

    if (extractButton) {
      extractButton.disabled = true;
    }

    try {
      setStatus("Preparing CSV export...");
      const exportRows = await buildFailureExportRows();

      const headers = ["UMR", "Test ID", "Field Name", "Value", "Severity", "Exception ID", "Test Type", "Description"];
      const rowsForCsv = [headers, ...exportRows.map((row) => [
        row.umr,
        row.testId,
        row.fieldName,
        row.value,
        row.severity,
        row.exceptionId || "",
        row.testType || "",
        row.description,
      ])];
      const csvEscape = (input) => `"${String(input ?? "").replace(/"/g, '""')}"`;
      const csvContent = rowsForCsv.map((row) => row.map(csvEscape).join(",")).join("\n");

      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      const link = document.createElement("a");
      link.href = url;
      link.download = `axios_${timestamp}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      setStatus(`Export complete: ${exportRows.length} failure rows downloaded as CSV.`);
    } catch (error) {
      setStatus(`Extract failed: ${error?.message || "Unexpected error"}`, true);
    } finally {
      if (extractButton) {
        extractButton.disabled = false;
      }
    }
  }

  global.TaskpaneExtraction = {
    extractValidationResults,
  };
}(window));
