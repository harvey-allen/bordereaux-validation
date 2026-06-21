/**
 * Configuration factory for environment-specific settings
 * Automatically selects appropriate config based on ENVIRONMENT variable
 * Injected at build time via environment variable or loads from separate config files
 */

/**
 * Development configuration - local machine with http-server
 * Backend on localhost:8000 (direct connection)
 */
const CONFIG_DEVELOPMENT = {
  BACKEND_URL: "https://localhost:8000",
  API_KEY: "dev_bordereaux_key_12345",
  DEFAULT_PACK: "risk_and_premium",
  DEFAULT_REF_COLUMN: "ID",
  MAX_CELLS_PER_CHUNK: 5000,
  HEATMAP_FAIL_CAP: 10,
};

/**
 * Staging configuration - via nginx reverse proxy
 * Backend on nginx:443/api (production-like)
 */
const CONFIG_STAGING = {
  BACKEND_URL: "https://localhost/api",
  API_KEY: "${DEV_API_KEY_STAGING}",
  DEFAULT_PACK: "risk_and_premium",
  DEFAULT_REF_COLUMN: "ID",
  MAX_CELLS_PER_CHUNK: 5000,
  HEATMAP_FAIL_CAP: 10,
};

/**
 * Production configuration - via CloudFront CDN and ALB
 * Backend on production ALB with proper domain
 */
const CONFIG_PRODUCTION = {
  BACKEND_URL: "${BACKEND_API_URL}",
  API_KEY: "${PRODUCTION_API_KEY}",
  DEFAULT_PACK: "risk_and_premium",
  DEFAULT_REF_COLUMN: "ID",
  MAX_CELLS_PER_CHUNK: 5000,
  HEATMAP_FAIL_CAP: 10,
};

/**
 * Get configuration based on ENVIRONMENT variable
 * Falls back to development if ENVIRONMENT is not set or unrecognized
 * ENVIRONMENT is injected at runtime via:
 * 1. window.__ENV__ (injected by build script or html)
 * 2. window.ENVIRONMENT (global variable)
 * 3. Data attribute on script tag (data-environment)
 * @returns {Object} Configuration object
 */
function getConfig() {
  let environment = "development";
  
  // Check multiple injection points
  if (typeof window !== "undefined") {
    if (window.__ENV__) {
      environment = window.__ENV__;
    } else if (window.ENVIRONMENT) {
      environment = window.ENVIRONMENT;
    }
  }

  switch (environment.toLowerCase()) {
    case "production":
      return CONFIG_PRODUCTION;
    case "staging":
      return CONFIG_STAGING;
    case "development":
    default:
      return CONFIG_DEVELOPMENT;
  }
}

// Export CONFIG at module load time
const CONFIG = getConfig();
