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

  global.NogaTelegram = {
    init: initTelegram,
    getInitData: getInitData,
    isTelegramContext: isTelegramContext,
    getWebApp: getWebApp,
  };
})(window);
