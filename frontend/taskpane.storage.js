(function initTaskpaneStorage(global) {
  const STORAGE_KEY_RESULTS = "bordereau_validation_results";
  const STORAGE_KEY_RESULTS_BY_SCOPE = "bordereau_validation_results_by_scope";

  function loadScopedMap() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY_RESULTS_BY_SCOPE);
      const parsed = raw ? JSON.parse(raw) : {};
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed;
      }
    } catch (error) {
      console.warn("Failed to load scoped validation results:", error);
    }
    return {};
  }

  function saveScopedMap(map) {
    try {
      const payload = map && typeof map === "object" && !Array.isArray(map) ? map : {};
      localStorage.setItem(STORAGE_KEY_RESULTS_BY_SCOPE, JSON.stringify(payload));
      return true;
    } catch (error) {
      console.warn("Failed to save scoped validation results:", error);
      return false;
    }
  }

  function getLatestScopedSnapshot(map) {
    const entries = Object.values(map || {}).filter((item) => item && typeof item === "object");
    if (entries.length === 0) {
      return null;
    }

    entries.sort((a, b) => {
      const at = Date.parse(String(a.timestamp || "")) || 0;
      const bt = Date.parse(String(b.timestamp || "")) || 0;
      return bt - at;
    });

    return entries[0] || null;
  }

  function persist(snapshot, options = {}) {
    const scopeKey = String(options?.scopeKey || "").trim();
    const payload = {
      ...snapshot,
      timestamp: new Date().toISOString(),
    };

    try {
      if (scopeKey) {
        const scopedMap = loadScopedMap();
        scopedMap[scopeKey] = payload;
        if (!saveScopedMap(scopedMap)) {
          return false;
        }
      }

      // Keep legacy latest snapshot key for backward compatibility.
      localStorage.setItem(STORAGE_KEY_RESULTS, JSON.stringify(payload));
      return true;
    } catch (error) {
      console.warn("Failed to persist validation results:", error);
      return false;
    }
  }

  function restore(options = {}) {
    const scopeKey = String(options?.scopeKey || "").trim();

    try {
      const scopedMap = loadScopedMap();
      if (scopeKey) {
        const scopedPayload = scopedMap[scopeKey];
        if (scopedPayload && typeof scopedPayload === "object") {
          return scopedPayload;
        }
      } else {
        const latestScoped = getLatestScopedSnapshot(scopedMap);
        if (latestScoped) {
          return latestScoped;
        }
      }

      const stored = localStorage.getItem(STORAGE_KEY_RESULTS);
      if (!stored) {
        return null;
      }
      const payload = JSON.parse(stored);
      return payload && typeof payload === "object" ? payload : null;
    } catch (error) {
      console.warn("Failed to restore validation results:", error);
      return null;
    }
  }

  function clear(options = {}) {
    const scopeKey = String(options?.scopeKey || "").trim();

    try {
      if (scopeKey) {
        const scopedMap = loadScopedMap();
        if (Object.prototype.hasOwnProperty.call(scopedMap, scopeKey)) {
          delete scopedMap[scopeKey];
          saveScopedMap(scopedMap);
        }
        return true;
      }

      localStorage.removeItem(STORAGE_KEY_RESULTS_BY_SCOPE);
      localStorage.removeItem(STORAGE_KEY_RESULTS);
      return true;
    } catch (error) {
      console.warn("Failed to clear validation results:", error);
      return false;
    }
  }

  global.TaskpaneStorage = {
    persist,
    restore,
    clear,
  };
}(window));
