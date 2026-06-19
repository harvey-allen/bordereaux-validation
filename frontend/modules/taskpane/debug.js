(function initTaskpaneDebugHelpers(global) {
  const STORAGE_KEY = String(
    (global.TaskpaneConstants || {}).DEBUG_LOG_STORAGE_KEY || "bordereaux_validator_debug_log"
  );

  function appendDebugLog(message, metadata = null) {
    try {
      const entry = {
        at: new Date().toISOString(),
        message: String(message || ""),
        metadata: metadata && typeof metadata === "object" ? metadata : null,
      };
      const existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      const next = Array.isArray(existing) ? existing : [];
      next.push(entry);
      const trimmed = next.slice(-200);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
      if (entry.metadata) {
        console.log("[BV-DEBUG]", entry.message, entry.metadata);
      } else {
        console.log("[BV-DEBUG]", entry.message);
      }
    } catch {
      // best-effort logging only
    }
  }

  function getDebugLogs() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    } catch {
      return [];
    }
  }

  function clearDebugLogs() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }

  global.TaskpaneDebug = {
    appendDebugLog,
    getDebugLogs,
    clearDebugLogs,
  };
}(window));
