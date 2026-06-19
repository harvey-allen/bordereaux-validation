(function initTaskpaneExceptionHelpers(global) {
  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function truncateText(text, maxLength = 16) {
    if (!text) return "";
    return text.length > maxLength ? text.substring(0, maxLength) + "..." : text;
  }

  function normalizeExceptionMatchValue(value) {
    return String(value || "").trim().toLowerCase();
  }

  function buildLinkedExceptionLookup(exceptions) {
    const lookup = new Map();

    for (const rawException of exceptions || []) {
      const exceptionId = String(rawException?.exception_id || "").trim();
      const linkedField = String(rawException?.linked_field || rawException?.test_id || "").trim();
      const linkedUmr = String(rawException?.linked_umr || "").trim();

      if (!exceptionId || !linkedField || !linkedUmr) {
        continue;
      }

      const key = `${normalizeExceptionMatchValue(linkedUmr)}::${normalizeExceptionMatchValue(linkedField)}`;
      if (!lookup.has(key)) {
        lookup.set(key, {
          exception_id: exceptionId,
          linked_field: linkedField,
          linked_umr: linkedUmr,
        });
      }
    }

    return lookup;
  }

  global.TaskpaneExceptions = {
    escapeHtml,
    truncateText,
    normalizeExceptionMatchValue,
    buildLinkedExceptionLookup,
  };
}(window));
