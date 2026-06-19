(function initTaskpaneTaggedCellHelpers(global) {
  const EXCEPTION_TAG_FILL = String(
    (global.TaskpaneConstants || {}).EXCEPTION_TAG_FILL || "#dbeafe"
  );

  function normalizeTaggedCellRecord(item) {
    if (!item || typeof item !== "object") {
      return null;
    }

    const address = String(item.address || "").trim().toUpperCase();
    const exceptionId = String(item.exception_id || item.exceptionId || "").trim();
    if (!address || !exceptionId) {
      return null;
    }

    return {
      address,
      exception_id: exceptionId,
      comment: String(item.comment || `Exception tagged: ${exceptionId}`).trim(),
      fill_color: String(item.fill_color || item.fillColor || EXCEPTION_TAG_FILL).trim() || EXCEPTION_TAG_FILL,
      previous_fill_color: String(item.previous_fill_color || item.previousFillColor || "").trim(),
      sheet_name: String(item.sheet_name || item.sheetName || "").trim(),
      workbook_name: String(item.workbook_name || item.workbookName || "").trim(),
      tagged_at: String(item.tagged_at || item.taggedAt || new Date().toISOString()).trim(),
    };
  }

  function mergeTaggedCells(existingItems, incomingItems) {
    const merged = new Map();
    for (const rawItem of existingItems || []) {
      const item = normalizeTaggedCellRecord(rawItem);
      if (!item) {
        continue;
      }
      merged.set(`${item.workbook_name}::${item.sheet_name}::${item.address}`, item);
    }
    for (const rawItem of incomingItems || []) {
      const item = normalizeTaggedCellRecord(rawItem);
      if (!item) {
        continue;
      }
      merged.set(`${item.workbook_name}::${item.sheet_name}::${item.address}`, item);
    }
    return Array.from(merged.values());
  }

  global.TaskpaneTaggedCells = {
    normalizeTaggedCellRecord,
    mergeTaggedCells,
  };
}(window));
