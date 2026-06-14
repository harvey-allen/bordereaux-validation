(function initTaskpanePackHelpers(global) {
  const DEFAULT_PACK_OPTIONS = [
    { value: "risk_and_premium", label: "Risk and Premium" },
    { value: "claims", label: "Claims" },
  ];

  function formatPackLabel(packName) {
    const normalized = String(packName || "").trim();
    if (!normalized) {
      return "";
    }
    return normalized
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function getDefaultPackValues() {
    return DEFAULT_PACK_OPTIONS.map((pack) => pack.value);
  }

  function getPackLabel(packName) {
    const normalized = String(packName || "").trim().toLowerCase();
    const known = DEFAULT_PACK_OPTIONS.find((pack) => pack.value === normalized);
    return known?.label || formatPackLabel(normalized);
  }

  function formatTestTypeLabel(testType) {
    return String(testType || "").trim().replace(/[_-]+/g, " ");
  }

  function populatePackSelect(packValues) {
    const select = document.getElementById("testPacks");
    if (!select) {
      return [];
    }

    const normalizedValues = Array.from(new Set(
      (Array.isArray(packValues) ? packValues : [])
        .map((value) => String(value || "").trim().toLowerCase())
        .filter(Boolean)
    ));

    const valuesToRender = normalizedValues.length > 0 ? normalizedValues : getDefaultPackValues();

    select.innerHTML = "";
    for (const packName of valuesToRender) {
      const option = document.createElement("option");
      option.value = packName;
      option.textContent = getPackLabel(packName);
      select.appendChild(option);
    }

    return valuesToRender;
  }

  async function loadSubscribedPackValues(excelUserEmail) {
    try {
      const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/test-packs`, {
        method: "GET",
        headers: {
          "X-Excel-User-Email": excelUserEmail,
        },
        cache: "no-store",
      });

      if (!response.ok) {
        return getDefaultPackValues();
      }

      const payload = await response.json().catch(() => ({}));
      const allowedPacks = Array.isArray(payload?.allowed_packs)
        ? payload.allowed_packs
        : (Array.isArray(payload?.all_packs) ? payload.all_packs : []);

      const normalized = Array.from(new Set(
        allowedPacks
          .map((value) => String(value || "").trim().toLowerCase())
          .filter(Boolean)
      ));

      return normalized.length > 0 ? normalized : getDefaultPackValues();
    } catch {
      return getDefaultPackValues();
    }
  }

  async function estimateFieldMapping(excelUserEmail, testPack, territory, headerValues) {
    try {
      const response = await fetch(`${CONFIG.BACKEND_URL}/api/v1/field-config/estimate-mapping`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Excel-User-Email": excelUserEmail,
        },
        body: JSON.stringify({
          test_pack: testPack,
          territory: territory,
          headers: Array.isArray(headerValues) ? headerValues : [],
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMessage = errorData.detail || errorData.message || `HTTP ${response.status}`;
        throw new Error(String(errorMessage));
      }

      return await response.json();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error || "Unknown error");
      throw new Error(errorMessage);
    }
  }

  global.TaskpanePacks = {
    formatPackLabel,
    getDefaultPackValues,
    getPackLabel,
    formatTestTypeLabel,
    populatePackSelect,
    loadSubscribedPackValues,
    estimateFieldMapping,
  };
}(window));
