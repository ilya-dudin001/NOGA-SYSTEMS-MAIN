(function (global) {
  "use strict";

  var dashboard = global.NogaDashboard;
  var views = global.NogaViews;
  var originalApplySummary = dashboard.applySummary;
  var originalApplyUser = dashboard.applyUser;
  var originalShow = views.show;
  var attentionRequest = 0;

  function setText(id, value) {
    var node = document.getElementById(id);
    if (node) node.textContent = String(value || 0);
  }

  function applySummary(summary) {
    originalApplySummary(summary);
    var trubki = (summary && summary.trubki) || {};
    var cities = (summary && summary.cities) || {};
    setText("navyPipelineTotal", trubki.total);
    setText("navyZacep", trubki.zacep);
    setText("navyVedut", trubki.vedut);
    setText("navySrez", trubki.srez);
    setText("navyZabrali", trubki.zabrali);
    setText("navyDone", trubki.razgruzheno);
    setText("navyMapCities", cities.total);
    setText("navyMapNogas", cities.nogas);
    updateAttention();
  }

  function applyUser(user) {
    originalApplyUser(user);
  }

  function showView(id) {
    originalShow(id);
    document.body.setAttribute("data-active-view", id);
    var view = document.getElementById(id);
    if (view) {
      view.classList.remove("navy-view-enter");
      void view.offsetWidth;
      view.classList.add("navy-view-enter");
    }
  }

  function formatDate() {
    var node = document.getElementById("navyDate");
    if (!node) return;
    var now = new Date();
    var date = now.toLocaleDateString("ru-RU", {
      day: "numeric",
      month: "long",
    });
    var time = now.toLocaleTimeString("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
    });
    node.textContent = date + " · " + time;
  }

  function addToolbarKickers() {
    var labels = {
      viewUsers: "Команда и доступ",
      viewNogas: "Исполнители",
      viewCities: "География операций",
      viewRazgruzy: "Сервисы переводов",
      viewTrubki: "Поток операций",
      viewTrubka: "Карточка операции",
      viewProfile: "Учётная запись",
      viewStats: "Сводные показатели",
    };
    Object.keys(labels).forEach(function (viewId) {
      var view = document.getElementById(viewId);
      var toolbar = view && view.querySelector(".users-toolbar");
      if (!toolbar || toolbar.querySelector(".navy-toolbar__kicker")) return;
      var kicker = document.createElement("span");
      kicker.className = "navy-toolbar__kicker";
      kicker.textContent = labels[viewId];
      toolbar.insertBefore(kicker, toolbar.firstChild);
    });
  }

  function addCityMap() {
    var modes = document.getElementById("citiesModes");
    if (!modes || document.getElementById("navyCityMap")) return;
    var map = document.createElement("section");
    map.className = "navy-city-map";
    map.id = "navyCityMap";
    map.setAttribute("aria-label", "Обзор географии");
    map.innerHTML =
      '<div class="navy-city-map__grid" aria-hidden="true"></div>' +
      '<i class="navy-city-map__pin navy-city-map__pin--one" aria-hidden="true"><span>Москва</span></i>' +
      '<i class="navy-city-map__pin navy-city-map__pin--two" aria-hidden="true"><span>Казань</span></i>' +
      '<i class="navy-city-map__pin navy-city-map__pin--three" aria-hidden="true"><span>Самара</span></i>' +
      '<i class="navy-city-map__pin navy-city-map__pin--alert" aria-hidden="true"><span>Фокус</span></i>' +
      '<p><span><b id="navyMapCities">—</b> городов</span><span><b id="navyMapNogas">—</b> ног</span></p>';
    modes.parentNode.insertBefore(map, modes);
  }

  async function updateAttention() {
    var card = document.getElementById("navyAttention");
    if (!card) return;
    if (!global.NogaRoles.can("cities:read")) {
      card.hidden = true;
      return;
    }

    attentionRequest += 1;
    var request = attentionRequest;
    try {
      var cities = await global.NogaApi.listCities("working");
      if (request !== attentionRequest) return;
      var seesRazgruzy = global.NogaRoles.can("razgruz:read");
      var problems = [];
      (cities || []).forEach(function (city) {
        var reasons = [];
        if (!city.nogas_count) reasons.push("нет ног");
        if (seesRazgruzy && !(city.razgruzy || []).length) reasons.push("нет разгруза");
        if (reasons.length) problems.push(city.name + ": " + reasons.join(", "));
      });

      if (!problems.length) {
        card.hidden = true;
        return;
      }

      var title = document.getElementById("navyAttentionTitle");
      var text = document.getElementById("navyAttentionText");
      if (title) title.textContent = "Требуют внимания: " + problems.length;
      if (text) text.textContent = problems.slice(0, 3).join(" · ");
      card.hidden = false;
    } catch (err) {
      if (request === attentionRequest) card.hidden = true;
    }
  }

  function bindAttention() {
    var button = document.getElementById("navyAttentionOpen");
    if (!button) return;
    button.addEventListener("click", function () {
      global.NogaProfile.hideBack();
      global.NogaCities.show({ mode: "working" });
      global.NogaRoles.activateTab("cities");
    });
  }

  dashboard.applySummary = applySummary;
  dashboard.applyUser = applyUser;
  views.show = showView;

  formatDate();
  addToolbarKickers();
  addCityMap();
  bindAttention();
})(window);
