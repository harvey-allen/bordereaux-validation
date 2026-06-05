(function initTaskpaneStorage(global) {
  const STORAGE_KEY_RESULTS = "bordereau_validation_results";

  function persist(snapshot) {
    try {
      localStorage.setItem(STORAGE_KEY_RESULTS, JSON.stringify({
        ...snapshot,
        timestamp: new Date().toISOString(),
      }));
      return true;
    } catch (error) {
      console.warn("Failed to persist validation results:", error);
      return false;
    }
  }

  function restore() {
    try {
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

  function clear() {
    try {
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
