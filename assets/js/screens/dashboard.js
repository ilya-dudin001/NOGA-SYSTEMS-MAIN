(function (global) {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function format(n) {
    return global.NogaDict.formatNumber(n);
  }

  function countUp(el, target, duration) {
    var start = performance.now();
    function frame(now) {
      var p = Math.min((now - start) / duration, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = format(Math.round(target * eased));
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function setCount(el, value, animate) {
    var target = Number(value) || 0;
    if (reduceMotion || animate === false) {
      el.textContent = format(target);
      return;
    }
    el.textContent = format(0);
    countUp(el, target, 900);
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

  function applySummary(summary, options) {
    summary = summary || {};
    var animate = !options || options.animate !== false;
    var map = {
      "stat-created": summary.created,
      "stat-in-progress": summary.in_progress,
      "stat-entries": summary.entries,
      "stat-paid": summary.paid,
      "stat-remaining": summary.remaining,
      "stat-total": summary.total_operations,
      "turn-rub": summary.turnover_rub,
      "turn-usd": summary.turnover_usd,
    };
    Object.keys(map).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) setCount(el, map[id] || 0, animate);
    });

    applyCities(summary.cities || {});

    var turnover = document.getElementById("turnoverCard");
    if (turnover) {
      if (summary.scope === "own" || !global.NogaRoles.can("dashboard:global")) {
        turnover.classList.add("is-hidden-by-role");
      } else {
        turnover.classList.remove("is-hidden-by-role");
      }
    }

    var list = document.getElementById("opList");
    if (list) {
      var ops = summary.recent_operations || [];
      if (!ops.length) {
        list.innerHTML =
          '<li class="empty-hint" style="list-style:none;padding:8px 4px">Пока нет операций</li>';
      }
    }
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
        var name = tab.getAttribute("data-tab");
        if (name === "profile" && (global.NogaRoles.can("users:manage") || global.NogaRoles.can("users:read"))) {
          /* profile tab can open users for managers — handled in app.js */
        }
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
