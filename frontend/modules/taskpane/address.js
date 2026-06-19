(function initTaskpaneAddressHelpers(global) {
  function excelColToNumber(col) {
    let num = 0;
    for (let i = 0; i < col.length; i += 1) {
      num = num * 26 + (col.charCodeAt(i) - 64);
    }
    return num;
  }

  function numberToExcelCol(num) {
    let col = "";
    while (num > 0) {
      num -= 1;
      col = String.fromCharCode((num % 26) + 65) + col;
      num = Math.floor(num / 26);
    }
    return col;
  }

  function parseCell(cellStr) {
    const normalized = String(cellStr || "").replace(/\$/g, "").trim().toUpperCase();
    const match = normalized.match(/^([A-Z]+)(\d+)$/);
    if (!match) {
      return null;
    }

    const col = excelColToNumber(match[1]);
    const row = parseInt(match[2], 10);

    return { col, row };
  }

  function parseExcelAddress(address) {
    if (!address) {
      return [];
    }

    const parts = address.split("!");
    if (parts.length < 2) {
      return [];
    }

    const rangePart = parts[1];
    const colonIndex = rangePart.indexOf(":");
    const addresses = [];

    if (colonIndex === -1) {
      addresses.push(rangePart);
    } else {
      const [startCell, endCell] = rangePart.split(":");
      const start = parseCell(startCell);
      const end = parseCell(endCell);

      if (start && end) {
        for (let row = start.row; row <= end.row; row += 1) {
          for (let col = start.col; col <= end.col; col += 1) {
            addresses.push(`${numberToExcelCol(col)}${row}`);
          }
        }
      }
    }

    return addresses;
  }

  global.TaskpaneAddress = {
    parseExcelAddress,
    parseCell,
    excelColToNumber,
    numberToExcelCol,
  };
}(window));
