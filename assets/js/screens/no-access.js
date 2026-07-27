(function (global) {
  "use strict";

  function show(code, message) {
    var gate = document.getElementById("gate");
    var appMain = document.getElementById("appMain");
    var tabbar = document.getElementById("tabbar");
    var splash = document.getElementById("splash");
    var title = document.getElementById("gateTitle");
    var text = document.getElementById("gateText");
    var codeEl = document.getElementById("gateCode");

    if (splash) splash.classList.add("is-hidden");
    if (appMain) appMain.hidden = true;
    if (tabbar) tabbar.hidden = true;
    if (gate) {
      gate.classList.add("is-visible");
      gate.hidden = false;
    }
    if (title) title.textContent = "Доступ закрыт";
    if (text) {
      text.textContent =
        message ||
        "Этот бот и веб-приложение доступны только участникам NOGA Systems. Обратитесь к Owner.";
    }
    if (codeEl) codeEl.textContent = code ? "Код: " + code : "";
  }

  function hide() {
    var gate = document.getElementById("gate");
    if (gate) {
      gate.classList.remove("is-visible");
      gate.hidden = true;
    }
  }

  global.NogaNoAccess = { show: show, hide: hide };
})(window);
