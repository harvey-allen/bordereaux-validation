(function initTaskpaneSheetRange(global) {
  function columnToA1(colIndexZeroBased) {
    let dividend = colIndexZeroBased + 1;
    let columnName = "";

    while (dividend > 0) {
      const modulo = (dividend - 1) % 26;
      columnName = String.fromCharCode(65 + modulo) + columnName;
      dividend = Math.floor((dividend - modulo) / 26);
    }

    return columnName;
  }

  function buildAddressRow(globalRowZeroBased, startColZeroBased, columnCount) {
    const rowNumber = globalRowZeroBased + 1;
    const rowAddresses = [];

    for (let colOffset = 0; colOffset < columnCount; colOffset += 1) {
      const colName = columnToA1(startColZeroBased + colOffset);
      rowAddresses.push(`${colName}${rowNumber}`);
    }

    return rowAddresses;
  }

  function isCellEmpty(value) {
    return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
  }

  function findNonEmptyBounds(values) {
    if (!Array.isArray(values) || values.length === 0) {
      return null;
    }

    let minRow = Number.POSITIVE_INFINITY;
    let maxRow = Number.NEGATIVE_INFINITY;
    let minCol = Number.POSITIVE_INFINITY;
    let maxCol = Number.NEGATIVE_INFINITY;

    for (let r = 0; r < values.length; r += 1) {
      const row = values[r] || [];
      for (let c = 0; c < row.length; c += 1) {
        if (!isCellEmpty(row[c])) {
          minRow = Math.min(minRow, r);
          maxRow = Math.max(maxRow, r);
          minCol = Math.min(minCol, c);
          maxCol = Math.max(maxCol, c);
        }
      }
    }

    if (!Number.isFinite(minRow)) {
      return null;
    }

    return { minRow, maxRow, minCol, maxCol };
  }

  async function resolveValidationRangeMeta() {
    return Excel.run(async (context) => {
      const workbook = context.workbook;
      const worksheet = workbook.worksheets.getActiveWorksheet();
      const selectedRange = workbook.getSelectedRange();

      worksheet.load(["name"]);
      selectedRange.load(["rowIndex", "columnIndex", "rowCount", "columnCount", "values"]);
      await context.sync();

      const selectionHasHeaderAndData = selectedRange.rowCount >= 2 && selectedRange.columnCount >= 1;
      if (selectionHasHeaderAndData) {
        const headerValues = selectedRange.values?.[0] || [];
        const hasHeaderContent = headerValues.some((value) => !isCellEmpty(value));
        if (hasHeaderContent) {
          return {
            startRow: selectedRange.rowIndex,
            startCol: selectedRange.columnIndex,
            rowCount: selectedRange.rowCount,
            columnCount: selectedRange.columnCount,
            headerValues,
            headerAddresses: buildAddressRow(
              selectedRange.rowIndex,
              selectedRange.columnIndex,
              selectedRange.columnCount
            ),
            sheetName: worksheet.name,
            source: "selection",
          };
        }
      }

      const usedRange = worksheet.getUsedRangeOrNullObject();
      usedRange.load(["isNullObject", "rowIndex", "columnIndex", "rowCount", "columnCount", "values"]);
      await context.sync();

      if (usedRange.isNullObject) {
        throw new Error("No data found on the active sheet.");
      }

      const bounds = findNonEmptyBounds(usedRange.values || []);
      if (!bounds) {
        throw new Error("No data found on the active sheet.");
      }

      const trimmedStartRow = usedRange.rowIndex + bounds.minRow;
      const trimmedStartCol = usedRange.columnIndex + bounds.minCol;
      const trimmedRowCount = bounds.maxRow - bounds.minRow + 1;
      const trimmedColumnCount = bounds.maxCol - bounds.minCol + 1;

      if (trimmedRowCount < 2) {
        throw new Error("Could not identify a table with a header row and at least one data row.");
      }

      const headerValues = (usedRange.values[bounds.minRow] || []).slice(bounds.minCol, bounds.maxCol + 1);

      return {
        startRow: trimmedStartRow,
        startCol: trimmedStartCol,
        rowCount: trimmedRowCount,
        columnCount: trimmedColumnCount,
        headerValues,
        headerAddresses: buildAddressRow(trimmedStartRow, trimmedStartCol, trimmedColumnCount),
        sheetName: worksheet.name,
        source: "sheet",
      };
    });
  }

  async function readRangeValues(startRow, startCol, rowCount, columnCount) {
    return Excel.run(async (context) => {
      const worksheet = context.workbook.worksheets.getActiveWorksheet();
      const range = worksheet.getRangeByIndexes(startRow, startCol, rowCount, columnCount);
      range.load("values");
      await context.sync();
      return range.values;
    });
  }

  async function buildCurrentSheetDataPayload() {
    const tableMeta = await resolveValidationRangeMeta();
    const dataRowCount = Math.max(0, Number(tableMeta.rowCount || 0) - 1);
    if (dataRowCount === 0) {
      return [];
    }

    const rows = await readRangeValues(
      tableMeta.startRow + 1,
      tableMeta.startCol,
      dataRowCount,
      tableMeta.columnCount
    );

    const headers = Array.from({ length: tableMeta.columnCount }, (_, index) => {
      const rawHeader = tableMeta.headerValues?.[index];
      const normalized = String(rawHeader ?? "").trim();
      return normalized || `column_${index + 1}`;
    });

    return rows.map((rowValues) => {
      const rowObj = {};
      for (let index = 0; index < headers.length; index += 1) {
        rowObj[headers[index]] = Array.isArray(rowValues) ? rowValues[index] : null;
      }
      return rowObj;
    });
  }

  async function clearCommentsInRange(startRow, startCol, rowCount, columnCount) {
    await Excel.run(async (context) => {
      const worksheet = context.workbook.worksheets.getActiveWorksheet();
      const comments = worksheet.comments;
      comments.load("items");
      await context.sync();

      if (comments.items.length === 0) {
        return;
      }

      const addressSet = new Set();
      for (let r = 0; r < rowCount; r++) {
        for (let c = 0; c < columnCount; c++) {
          const colLetter = columnToA1(startCol + c);
          const rowNum = startRow + r + 1;
          addressSet.add(`${colLetter}${rowNum}`);
        }
      }

      const commentLocations = [];
      for (const comment of comments.items) {
        const location = comment.getLocation();
        location.load("address");
        commentLocations.push({ comment, location });
      }
      await context.sync();

      for (const { comment, location } of commentLocations) {
        const cellAddress = location.address;
        const cellPart = cellAddress.includes("!") ? cellAddress.split("!")[1] : cellAddress;
        if (addressSet.has(cellPart)) {
          comment.delete();
        }
      }

      await context.sync();
    });
  }

  global.TaskpaneSheetRange = {
    columnToA1,
    buildAddressRow,
    isCellEmpty,
    findNonEmptyBounds,
    resolveValidationRangeMeta,
    readRangeValues,
    buildCurrentSheetDataPayload,
    clearCommentsInRange,
  };
}(window));
