(function (global) {
  "use strict";

  function bind() {
    var button = document.getElementById("designSwitch");
    if (!button || button.dataset.bound) return;
    button.dataset.bound = "1";
    button.addEventListener("click", function () {
      var href = button.getAttribute("data-theme-href");
      if (!href) return;

      var target = new URL(href, global.location.href);
      var current = new URLSearchParams(global.location.search);
      var api = current.get("api");
      if (api) target.searchParams.set("api", api);

      // Telegram передаёт параметры Mini App в hash — сохраняем их при переходе.
      target.hash = global.location.hash;
      global.location.assign(target.toString());
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})(window);
