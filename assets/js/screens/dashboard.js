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
    // #region agent log
    requestAnimationFrame(function () {
      var topbar = document.querySelector(".topbar");
      var brand = document.querySelector(".topbar__brand");
      var logo = document.querySelector(".topbar .logo");
      var name = document.querySelector(".topbar__name");
      var role = document.querySelector(".topbar__role");
      var app = document.querySelector(".app");
      var bell = document.querySelector(".bell");
      function box(el) {
        if (!el) return null;
        var r = el.getBoundingClientRect();
        return {
          left: +r.left.toFixed(2),
          right: +r.right.toFixed(2),
          width: +r.width.toFixed(2),
          center: +(r.left + r.width / 2).toFixed(2),
        };
      }
      var appBox = box(app);
      var logoBox = box(logo);
      var brandBox = box(brand);
      var nameBox = box(name);
      var roleBox = box(role);
      var topbarBox = box(topbar);
      var bellBox = box(bell);
      var pageCenter = appBox ? appBox.center : null;
      var data = {
        nameText: name && name.textContent,
        roleText: role && role.textContent,
        pageCenter: pageCenter,
        logoCenter: logoBox && logoBox.center,
        brandCenter: brandBox && brandBox.center,
        logoOffsetFromPage: logoBox && pageCenter != null ? +(logoBox.center - pageCenter).toFixed(2) : null,
        brandOffsetFromPage: brandBox && pageCenter != null ? +(brandBox.center - pageCenter).toFixed(2) : null,
        nameWidth: nameBox && nameBox.width,
        roleWidth: roleBox && roleBox.width,
        widthDeltaNameMinusRole:
          nameBox && roleBox ? +(nameBox.width - roleBox.width).toFixed(2) : null,
        topbarPadding: topbar
          ? {
              left: getComputedStyle(topbar).paddingLeft,
              right: getComputedStyle(topbar).paddingRight,
              display: getComputedStyle(topbar).display,
              justify: getComputedStyle(topbar).justifyContent,
            }
          : null,
        brandMaxWidth: brand ? getComputedStyle(brand).maxWidth : null,
        bellRight: bellBox && topbarBox ? +(topbarBox.right - bellBox.right).toFixed(2) : null,
        app: appBox,
        topbar: topbarBox,
        brand: brandBox,
        logo: logoBox,
        name: nameBox,
        role: roleBox,
      };
      fetch("http://127.0.0.1:7889/ingest/c7094e1d-b975-4054-9229-e7756754b3c2", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Debug-Session-Id": "b565fe",
        },
        body: JSON.stringify({
          sessionId: "b565fe",
          runId: "post-fix",
          hypothesisId: "A",
          location: "dashboard.js:applyUser",
          message: "topbar geometry after logo-center fix",
          data: data,
          timestamp: Date.now(),
        }),
      }).catch(function () {});
    });
    // #endregion
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
