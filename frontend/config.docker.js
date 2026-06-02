/**
 * Frontend configuration for Docker environment
 * Uses the nginx reverse proxy for HTTPS
 */
const CONFIG = {
  // Backend API URL via nginx reverse proxy (HTTPS)
  BACKEND_URL: "https://localhost/api",

  // API Key for authentication (get from your subscription)
  // Development key provided for testing
  API_KEY: "dev_bordereaux_key_12345",

  // Default test pack to select on load
  DEFAULT_PACK: "risk_and_premium",

  // Default reference column name
  DEFAULT_REF_COLUMN: "ID",

  // Maximum cells per validation chunk (to avoid payload size limits)
  MAX_CELLS_PER_CHUNK: 5000,

  // Heatmap severity rank cap (1-10)
  HEATMAP_FAIL_CAP: 10,
};
