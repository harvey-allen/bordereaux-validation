(function initTaskpaneScopeHelpers(global) {
  function buildSheetScopeKey(workbookName, sheetName) {
    const wb = String(workbookName || "__unknown_workbook__").trim() || "__unknown_workbook__";
    const sh = String(sheetName || "__unknown_sheet__").trim() || "__unknown_sheet__";
    return `${wb}::${sh}`;
  }

  global.TaskpaneScope = {
    buildSheetScopeKey,
  };
}(window));
