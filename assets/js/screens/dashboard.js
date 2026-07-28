(function (global) {
  "use strict";

  function format(n) {
    return global.NogaDict.formatNumber(n);
  }

  function applyCities(cities) {
    var card = document.getElementById("citiesCard");
    if (!card) return;
    if (!global.NogaRoles.can("cities:read")) {
      card.hidden = true;
      return;
    }
    card.hidden = false;

    var map = {
      citiesTotal: cities.total,
      citiesWorking: cities.working,
      citiesPaused: cities.paused,
      citiesStopped: cities.stopped,
    };
    Object.keys(map).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.textContent = format(map[id] || 0);
    });

    var foot = document.getElementById("citiesFoot");
    if (foot) {
      foot.textContent =
        "Ног: " + format(cities.nogas || 0) + " · Разгрузов: " + format(cities.razgruzy || 0);
    }
  }

  function applySummary(summary) {
    summary = summary || {};
    applyCities(summary.cities || {});
    global.NogaTrubki.applyTotal((summary.trubki || {}).total);
    global.NogaTrubki.renderDashboard();
  }

  function applyUser(user) {
    var nameEl = document.getElementById("greetingName");
    var roleEl = document.getElementById("greetingRole");
    if (nameEl) nameEl.textContent = user.display_name || "User";
    if (roleEl) roleEl.textContent = user.role_label || user.role || "";
  }

  function bindChrome() {
    var tabs = document.querySelectorAll(".tab[data-tab]");
    Array.prototype.forEach.call(tabs, function (tab) {
      tab.addEventListener("click", function () {
        Array.prototype.forEach.call(tabs, function (t) {
          t.classList.remove("is-active");
          t.removeAttribute("aria-current");
        });
        tab.classList.add("is-active");
        tab.setAttribute("aria-current", "page");
      });
    });

    var bell = document.getElementById("bell");
    if (bell) {
      bell.addEventListener("click", function () {
        bell.classList.toggle("has-alert");
      });
    }
  }

  global.NogaDashboard = {
    applySummary: applySummary,
    applyUser: applyUser,
    bindChrome: bindChrome,
    format: format,
  };
})(window);
