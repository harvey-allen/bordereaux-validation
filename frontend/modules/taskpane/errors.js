(function initTaskpaneErrorHelpers(global) {
  function buildFrontendErrorMessage(prefix, error) {
    const detail = error instanceof Error
      ? error.message
      : String(error?.message || error || "Unexpected error");
    return `${prefix}: ${detail}`;
  }

  function shouldSuppressFrontendError(error) {
    const message = String(error?.message || error || "").toLowerCase();
    return message.includes("invalid api call in the current context");
  }

  global.TaskpaneErrors = {
    buildFrontendErrorMessage,
    shouldSuppressFrontendError,
  };
}(window));
