/**
 * Frontend configuration
 * Edit these values or override via environment-specific config files
 */
const CONFIG = {
  // Backend API URL (HTTPS to avoid mixed content issues)
  BACKEND_URL: "https://127.0.0.1:8000",

  // API Key for authentication (get from your subscription)
  // Development key provided for testing
  API_KEY: "dev_bordereaux_key_12345",

  // Default test pack to select on load
  DEFAULT_PACK: "bordereaux",

  // Default reference column name
  DEFAULT_REF_COLUMN: "policy_id",

  // Maximum cells per validation chunk (to avoid payload size limits)
  MAX_CELLS_PER_CHUNK: 5000,

  // Heatmap color scale cap (failures beyond this value don't get darker)
  HEATMAP_FAIL_CAP: 8,
};
