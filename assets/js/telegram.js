(function (global) {
  "use strict";

  function getWebApp() {
    return global.Telegram && global.Telegram.WebApp ? global.Telegram.WebApp : null;
  }

  function initTelegram() {
    var wa = getWebApp();
    if (!wa) return null;
    try {
      wa.ready();
      if (typeof wa.expand === "function") wa.expand();
      if (wa.themeParams && wa.themeParams.bg_color) {
        document.documentElement.style.setProperty("--tg-bg", wa.themeParams.bg_color);
      }
    } catch (e) {
      /* ignore */
    }
    return wa;
  }

  function getInitData() {
    var wa = getWebApp();
    if (wa && wa.initData) return wa.initData;
    var params = new URLSearchParams(global.location.search);
    return params.get("tgWebAppData") || "";
  }

  function isTelegramContext() {
    return Boolean(getInitData());
  }

  /* window.confirm/alert are ignored inside the Telegram WebView, so prefer the native
     dialogs (Bot API 6.2+) and fall back to the browser ones. */
  function confirmAction(message, onConfirm) {
    var wa = getWebApp();
    if (wa && typeof wa.showConfirm === "function") {
      try {
        wa.showConfirm(message, function (ok) {
          if (ok) onConfirm();
        });
        return;
      } catch (e) {
        /* unsupported client version — fall through */
      }
    }
    if (global.confirm(message)) onConfirm();
  }

  function notify(message) {
    var wa = getWebApp();
    if (wa && typeof wa.showAlert === "function") {
      try {
        wa.showAlert(message);
        return;
      } catch (e) {
        /* unsupported client version — fall through */
      }
    }
    global.alert(message);
  }

  global.NogaTelegram = {
    init: initTelegram,
    getInitData: getInitData,
    isTelegramContext: isTelegramContext,
    getWebApp: getWebApp,
    confirmAction: confirmAction,
    notify: notify,
  };
})(window);
