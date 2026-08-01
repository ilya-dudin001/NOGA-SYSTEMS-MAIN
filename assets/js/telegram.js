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

  function getChatDeepLink() {
    var params = new URLSearchParams(global.location.search);
    var roomId = params.get("chat_room");
    var messageId = params.get("chat_message");

    var wa = getWebApp();
    if ((!roomId || !messageId) && wa && wa.initDataUnsafe) {
      var unsafe = wa.initDataUnsafe;
      if (unsafe.start_param) {
        /* startapp может прийти как chat_room_12_45 — не используем; params приоритетнее */
      }
    }
    if (!roomId && params.get("tgWebAppStartParam")) {
      /* deep link в основном через query webapp_url */
    }

    roomId = roomId ? Number(roomId) : null;
    messageId = messageId ? Number(messageId) : null;
    if (!roomId || isNaN(roomId)) return null;
    return {
      roomId: roomId,
      messageId: messageId && !isNaN(messageId) ? messageId : null,
    };
  }

  function clearChatDeepLink() {
    try {
      var url = new URL(global.location.href);
      if (!url.searchParams.has("chat_room") && !url.searchParams.has("chat_message")) {
        return;
      }
      url.searchParams.delete("chat_room");
      url.searchParams.delete("chat_message");
      global.history.replaceState({}, "", url.pathname + url.search + url.hash);
    } catch (e) {
      /* ignore */
    }
  }

  function getUiLang() {
    var wa = getWebApp();
    var code = "";
    try {
      if (wa && wa.initDataUnsafe && wa.initDataUnsafe.user) {
        code = wa.initDataUnsafe.user.language_code || "";
      }
    } catch (e) {
      /* ignore */
    }
    if (!code && global.navigator) {
      code = global.navigator.language || global.navigator.userLanguage || "";
    }
    code = String(code || "").toLowerCase();
    if (code.indexOf("ru") === 0) return "ru";
    if (code.indexOf("en") === 0) return "en";
    /* Документ по умолчанию русский (index.html lang=ru). */
    var htmlLang = (global.document && global.document.documentElement.lang) || "ru";
    return String(htmlLang).toLowerCase().indexOf("en") === 0 ? "en" : "ru";
  }

  global.NogaTelegram = {
    init: initTelegram,
    getInitData: getInitData,
    isTelegramContext: isTelegramContext,
    getWebApp: getWebApp,
    getUiLang: getUiLang,
    confirmAction: confirmAction,
    notify: notify,
    getChatDeepLink: getChatDeepLink,
    clearChatDeepLink: clearChatDeepLink,
  };
})(window);
