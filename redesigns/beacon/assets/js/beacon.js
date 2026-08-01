/* «Маяк»: дата в шапке, сводка стадий трубок, баннер внимания, переходы экранов. */
(function (global) {
  "use strict";

  var dashboard = global.NogaDashboard;
  var views = global.NogaViews;
  var originalApplySummary = dashboard.applySummary;
  var originalShow = views.show;
  var attentionRequest = 0;

  var STAGES = [
    { value: "zacep", label: "Зацеп", cls: "beacon-stage--zacep" },
    { value: "vedut", label: "Ведут", cls: "beacon-stage--vedut" },
    { value: "srez", label: "Срез", cls: "beacon-stage--srez" },
    { value: "zabrali", label: "Забрали", cls: "beacon-stage--zabrali" },
    { value: "razgruzheno", label: "Готово", cls: "beacon-stage--done" },
  ];

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  /* ---------- сводка стадий на дашборде ---------- */

  function buildStages() {
    var host = document.getElementById("beaconStages");
    if (!host || host.childNodes.length) return;
    STAGES.forEach(function (stage) {
      var btn = el("button", "beacon-stage " + stage.cls);
      btn.type = "button";
      btn.title = "Трубки: " + stage.label;
      btn.appendChild(el("span", "beacon-stage__num", "0"));
      btn.appendChild(el("span", "beacon-stage__label", stage.label));
      btn.addEventListener("click", function () {
        global.NogaProfile.hideBack();
        global.NogaTrubki.show({ status: stage.value });
        global.NogaRoles.activateTab("home");
      });
      host.appendChild(btn);
    });
  }

  function fillStages(trubki) {
    var host = document.getElementById("beaconStages");
    if (!host) return;
    var nums = host.querySelectorAll(".beacon-stage__num");
    STAGES.forEach(function (stage, index) {
      if (nums[index]) {
        nums[index].textContent = global.NogaDict.formatNumber(trubki[stage.value] || 0);
      }
    });
  }

  /* ---------- баннер «требуют внимания» ---------- */

  async function updateAttention() {
    var card = document.getElementById("beaconAttention");
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

      var title = document.getElementById("beaconAttentionTitle");
      var text = document.getElementById("beaconAttentionText");
      if (title) {
        title.textContent =
          problems.length === 1
            ? "Один город требует внимания"
            : "Города требуют внимания: " + problems.length;
      }
      if (text) text.textContent = problems.slice(0, 3).join(" · ");
      card.hidden = false;
    } catch (err) {
      if (request === attentionRequest) card.hidden = true;
    }
  }

  function bindAttention() {
    var button = document.getElementById("beaconAttentionOpen");
    if (!button) return;
    button.addEventListener("click", function () {
      global.NogaProfile.hideBack();
      global.NogaCities.show({ mode: "working" });
      global.NogaRoles.activateTab("cities");
    });
  }

  /* ---------- дата в шапке ---------- */

  function formatDate() {
    var node = document.getElementById("beaconDate");
    if (!node) return;
    var now = new Date();
    var text = now.toLocaleDateString("ru-RU", {
      weekday: "long",
      day: "numeric",
      month: "long",
    });
    node.textContent = text.charAt(0).toUpperCase() + text.slice(1);
  }

  /* ---------- обёртки ---------- */

  function applySummary(summary) {
    originalApplySummary(summary);
    fillStages((summary && summary.trubki) || {});
    updateAttention();
  }

  function showView(id) {
    originalShow(id);
    var view = document.getElementById(id);
    if (!view) return;
    view.classList.remove("beacon-view-enter");
    void view.offsetWidth;
    view.classList.add("beacon-view-enter");
  }

  dashboard.applySummary = applySummary;
  views.show = showView;

  buildStages();
  formatDate();
  bindAttention();
})(window);
