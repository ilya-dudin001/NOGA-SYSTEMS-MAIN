(function (global) {
  "use strict";

  async function applySession(auth) {
    global.NogaApi.setToken(auth.access_token);
    global.NogaRoles.setUser(auth.user);
    global.NogaNoAccess.hide();
    global.NogaDashboard.applyUser(auth.user);

    var splash = document.getElementById("splash");
    var appMain = document.getElementById("appMain");
    var tabbar = document.getElementById("tabbar");
    var gate = document.getElementById("gate");
    var devPanel = document.getElementById("devPanel");

    if (gate) {
      gate.hidden = true;
      gate.classList.remove("is-visible");
    }
    if (devPanel) devPanel.hidden = true;
    if (appMain) appMain.hidden = false;
    if (tabbar) tabbar.hidden = false;
    if (splash) splash.classList.add("is-hidden");

    var usersEntry = document.getElementById("usersEntry");
    if (usersEntry) {
      usersEntry.hidden = !(
        global.NogaRoles.can("users:manage") || global.NogaRoles.can("users:read")
      );
    }

    var nogasEntry = document.getElementById("nogasEntry");
    if (nogasEntry) {
      nogasEntry.hidden = !(
        global.NogaRoles.can("nogas:manage") || global.NogaRoles.can("nogas:read")
      );
    }

    var razgruzyEntry = document.getElementById("razgruzyEntry");
    if (razgruzyEntry) {
      razgruzyEntry.hidden = !(
        global.NogaRoles.can("razgruz:manage") || global.NogaRoles.can("razgruz:read")
      );
    }

    global.NogaRoles.applyTabbar();
    global.NogaViews.show("viewHome");

    try {
      var summary = await global.NogaApi.dashboardSummary();
      global.NogaDashboard.applySummary(summary);
    } catch (e) {
      global.NogaDashboard.applySummary({ scope: "global" });
    }
  }

  function showGateFromError(err) {
    var code = (err && err.code) || "ERROR";
    var msg = (err && err.message) || "Не удалось авторизоваться";
    if (code === "NOT_ALLOWED") {
      msg = "Ваш Telegram ID не в списке разрешённых. Обратитесь к Owner.";
    } else if (code === "BLOCKED") {
      msg = "Ваш доступ заблокирован.";
    } else if (code === "BAD_SIGNATURE" || code === "EXPIRED") {
      msg = "Данные Telegram недействительны. Закройте и откройте приложение снова.";
    } else if (code === "Failed to fetch" || String(msg).indexOf("fetch") !== -1) {
      msg = "API недоступен. Проверьте, что backend запущен, и параметр ?api=…";
      code = "API_UNREACHABLE";
    }
    global.NogaNoAccess.show(code, msg);
    maybeShowDevPanel();
  }

  function maybeShowDevPanel() {
    var cfg = global.NOGA_CONFIG || {};
    if (!cfg.allowDevLogin) return;
    if (global.NogaTelegram.isTelegramContext()) return;
    var panel = document.getElementById("devPanel");
    if (panel) panel.hidden = false;
  }

  async function bootstrap() {
    global.NogaTelegram.init();
    global.NogaDashboard.bindChrome();
    global.NogaApi.setUnauthorizedHandler(function () {
      global.NogaApi.setToken(null);
      global.NogaNoAccess.show("UNAUTHORIZED", "Сессия истекла. Откройте приложение снова.");
    });

    bindNav();
    bindDevForm();

    var initData = global.NogaTelegram.getInitData();
    if (initData) {
      try {
        var auth = await global.NogaApi.authTelegram(initData);
        await applySession(auth);
      } catch (err) {
        showGateFromError(err);
      }
      return;
    }

    // Browser without Telegram — show splash then gate/dev
    var splash = document.getElementById("splash");
    if (splash) splash.classList.add("is-hidden");
    global.NogaNoAccess.show(
      "NO_TELEGRAM",
      "Откройте приложение через Telegram-бота. Для локальной отладки используйте форму ниже (DEV_AUTH_ENABLED на сервере)."
    );
    maybeShowDevPanel();
  }

  function bindNav() {
    var tabs = document.querySelectorAll(".tab[data-tab]");
    Array.prototype.forEach.call(tabs, function (tabNode) {
      tabNode.addEventListener("click", function () {
        var name = tabNode.getAttribute("data-tab");
        // Заход не из профиля — возвращаться в него незачем.
        global.NogaProfile.hideBack();
        if (name === "home") {
          global.NogaViews.show("viewHome");
          return;
        }
        if (name === "nogas") {
          global.NogaNogas.show();
          return;
        }
        if (name === "cities") {
          // Из таббара открываем свой участок, из плашки на дашборде — общий.
          global.NogaCities.show({ mode: "own" });
          return;
        }
        if (name === "profile") {
          global.NogaProfile.show();
        }
      });
    });

    bindEntry("usersEntry", function () {
      global.NogaUsers.show();
    });
    bindEntry("nogasEntry", function () {
      global.NogaNogas.show();
    }, "nogas");
    bindEntry("citiesEntry", function () {
      global.NogaCities.show({ mode: "working" });
    }, "cities");
    bindEntry("razgruzyEntry", function () {
      global.NogaRazgruzy.show();
    });
  }

  function bindEntry(id, open, tabName) {
    var entry = document.getElementById(id);
    if (!entry) return;
    entry.addEventListener("click", function () {
      global.NogaProfile.hideBack();
      open();
      global.NogaRoles.activateTab(tabName || "profile");
    });
  }

  function bindDevForm() {
    var form = document.getElementById("devLoginForm");
    if (!form) return;
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var tid = document.getElementById("devTelegramId").value;
      var secret = document.getElementById("devSecret").value;
      try {
        var auth = await global.NogaApi.authDev(tid, secret);
        await applySession(auth);
      } catch (err) {
        window.alert((err && err.message) || "Dev login failed");
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }
})(window);
