(function (global) {
  "use strict";

  /* Проекция под Simplemaps RU Mercator SVG (viewBox 1000×666). */
  var MAP = {
    lonMin: 19.0,
    lonMax: 191.0,
    latMin: 41.2,
    latMax: 81.9,
    pad: 0.02,
  };

  function format(n) {
    return global.NogaDict.formatNumber(n);
  }

  function mercY(lat) {
    var clamped = Math.max(-85, Math.min(85, lat));
    return (
      (180 / Math.PI) *
      Math.log(Math.tan(Math.PI / 4 + (clamped * Math.PI) / 360))
    );
  }

  function project(lat, lon) {
    var lng = lon < 0 ? lon + 360 : lon;
    var my0 = mercY(MAP.latMin);
    var my1 = mercY(MAP.latMax);
    var x = (lng - MAP.lonMin) / (MAP.lonMax - MAP.lonMin);
    var y = (my1 - mercY(lat)) / (my1 - my0);
    var pad = MAP.pad;
    x = pad + (1 - 2 * pad) * x;
    y = pad + (1 - 2 * pad) * y;
    return { x: x * 100, y: y * 100 };
  }

  function statusClass(status) {
    if (status === "paused") return "geo-card__pin--paused";
    if (status === "stopped") return "geo-card__pin--stopped";
    return "geo-card__pin--working";
  }

  function statusLabel(status) {
    var info = global.NogaDict.cityStatus(status);
    return (info && info.label) || status;
  }

  function applyGeography(cities) {
    var card = document.getElementById("geoCard");
    var host = document.getElementById("geoMarkers");
    var empty = document.getElementById("geoEmpty");
    var hint = document.getElementById("geoHint");
    if (!card || !host) return;

    if (!global.NogaRoles.can("cities:read")) {
      card.hidden = true;
      return;
    }
    card.hidden = false;

    var list = cities.geography || [];
    var withCoords = list.filter(function (c) {
      return c.lat != null && c.lon != null;
    });

    host.textContent = "";
    withCoords.forEach(function (city, i) {
      var pos = project(city.lat, city.lon);
      if (pos.x < -2 || pos.x > 102 || pos.y < -2 || pos.y > 102) return;

      var pin = document.createElement("button");
      pin.type = "button";
      pin.className = "geo-card__pin " + statusClass(city.status);
      pin.style.left = pos.x.toFixed(2) + "%";
      pin.style.top = pos.y.toFixed(2) + "%";
      pin.style.setProperty("--i", String(i));
      pin.title = city.name + " — " + statusLabel(city.status);
      pin.setAttribute("aria-label", city.name + ", " + statusLabel(city.status));
      pin.addEventListener("click", function () {
        if (global.NogaCities && global.NogaCities.show) {
          global.NogaCities.show({ mode: "own" });
        }
      });
      host.appendChild(pin);
    });

    if (empty) empty.hidden = withCoords.length > 0;
    if (hint) {
      hint.textContent =
        withCoords.length > 0
          ? format(withCoords.length) + " на карте · " + format(list.length) + " всего"
          : list.length
            ? "координаты подгружаются…"
            : "нет городов";
    }
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
      foot.textContent = "Ног: " + format(cities.nogas || 0);
    }

    applyGeography(cities);
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

    /* Колокольчик открывает чат — обработчик в NogaChat.bind(). */
  }

  global.NogaDashboard = {
    applySummary: applySummary,
    applyUser: applyUser,
    bindChrome: bindChrome,
    format: format,
  };
})(window);
