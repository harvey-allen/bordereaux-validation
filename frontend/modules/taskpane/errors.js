(function initTaskpaneErrorHelpers(global) {
  function isVisibleElement(element) {
    return Boolean(element) && !element.classList.contains("hidden");
  }

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

  function recoverBlankTaskpane(message) {
    const launchScreen = document.getElementById("launchScreen");
    const mainAppShell = document.getElementById("mainAppShell");

    const launchVisible = isVisibleElement(launchScreen);
    const mainVisible = isVisibleElement(mainAppShell);
    if (launchVisible || mainVisible) {
      return false;
    }

    if (launchScreen) {
      launchScreen.classList.remove("hidden");
    }

    if (mainAppShell) {
      mainAppShell.classList.add("hidden");
    }

    const launchTitle = document.getElementById("launchTitle");
    const launchSubtitle = document.getElementById("launchSubtitle");
    const launchButton = document.getElementById("launchGetStarted");

    if (launchTitle) {
      launchTitle.textContent = "Something went wrong";
    }
    if (launchSubtitle) {
      launchSubtitle.textContent = String(message || "An unexpected error occurred. Please use Help or retry.");
    }
    if (launchButton) {
      launchButton.classList.add("hidden");
      launchButton.disabled = false;
    }

    return true;
  }

  global.TaskpaneErrors = {
    buildFrontendErrorMessage,
    shouldSuppressFrontendError,
    recoverBlankTaskpane,
  };
}(window));
