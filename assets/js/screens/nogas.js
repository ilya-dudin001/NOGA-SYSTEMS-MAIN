(function (global) {
  "use strict";

  var cities = [];
  var formBound = false;

  function canManage() {
    return global.NogaRoles.can("nogas:manage");
  }

  async function loadCities() {
    try {
      cities = await global.NogaApi.listCities();
    } catch (err) {
      cities = [];
    }
    fillCitySelect();
  }

  function fillCitySelect() {
    var select = document.getElementById("newNogaCity");
    if (!select) return;
    var previous = select.value;
    select.innerHTML = "";

    if (!cities.length) {
      var empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "Городов пока нет — добавьте новый";
      select.appendChild(empty);
    }

    cities.forEach(function (city) {
      var opt = document.createElement("option");
      opt.value = String(city.id);
      opt.textContent = city.is_active ? city.name : city.name + " (выкл.)";
      select.appendChild(opt);
    });

    var newOpt = document.createElement("option");
    newOpt.value = "__new__";
    newOpt.textContent = "+ Новый город";
    select.appendChild(newOpt);

    if (previous) select.value = previous;
    toggleNewCityField();
  }

  function toggleNewCityField() {
    var select = document.getElementById("newNogaCity");
    var wrap = document.getElementById("newCityWrap");
    var input = document.getElementById("newNogaCityName");
    if (!select || !wrap || !input) return;
    var isNew = select.value === "__new__" || !cities.length;
    wrap.hidden = !isNew;
    input.required = isNew;
  }

  async function loadAndRender() {
    var listEl = document.getElementById("nogasList");
    if (!listEl) return;
    listEl.innerHTML = '<p class="empty-hint">Загрузка…</p>';
    try {
      var nogas = await global.NogaApi.listNogas();
      renderList(nogas);
    } catch (err) {
      listEl.innerHTML =
        '<p class="empty-hint">Не удалось загрузить: ' +
        (err.message || err.code || "ошибка") +
        "</p>";
    }
  }

  function renderList(nogas) {
    var listEl = document.getElementById("nogasList");
    if (!nogas || !nogas.length) {
      listEl.innerHTML = '<p class="empty-hint">Ног пока нет</p>';
      return;
    }
    listEl.innerHTML = "";

    nogas.forEach(function (n) {
      var card = document.createElement("article");
      card.className = "user-card";
      card.innerHTML =
        '<div class="user-card__top">' +
        "<div>" +
        '<p class="user-card__name"></p>' +
        '<p class="user-card__meta"></p>' +
        "</div>" +
        '<div class="user-card__badges"></div>' +
        "</div>" +
        '<div class="user-card__actions"></div>';

      card.querySelector(".user-card__name").textContent = n.name;
      card.querySelector(".user-card__meta").textContent = n.city_name;

      var badges = card.querySelector(".user-card__badges");
      if (n.is_test) badges.appendChild(makeBadge("Тест", "user-card__badge--test"));
      if (!n.is_active) badges.appendChild(makeBadge("Выключена", "user-card__badge--blocked"));
      if (!n.is_test && n.is_active) badges.appendChild(makeBadge("Рабочая", ""));

      if (canManage()) {
        var actions = card.querySelector(".user-card__actions");
        actions.appendChild(
          makeBtn(n.is_test ? "Сделать рабочей" : "Сделать тестовой", function () {
            patch(n, { is_test: !n.is_test });
          })
        );
        actions.appendChild(
          makeBtn(
            n.is_active ? "Выключить" : "Включить",
            function () {
              patch(n, { is_active: !n.is_active });
            },
            n.is_active ? "btn-ghost--danger" : ""
          )
        );
        actions.appendChild(
          makeBtn(
            "Удалить",
            function () {
              removeNoga(n);
            },
            "btn-ghost--danger"
          )
        );
      }

      listEl.appendChild(card);
    });
  }

  function makeBadge(text, extraClass) {
    var span = document.createElement("span");
    span.className = "user-card__badge" + (extraClass ? " " + extraClass : "");
    span.textContent = text;
    return span;
  }

  function makeBtn(label, onClick, extraClass) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn-ghost" + (extraClass ? " " + extraClass : "");
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
  }

  async function patch(noga, payload) {
    try {
      await global.NogaApi.updateNoga(noga.id, payload);
      await loadAndRender();
    } catch (err) {
      global.NogaTelegram.notify(err.message || "Не удалось изменить");
    }
  }

  function removeNoga(noga) {
    var question = "Удалить ногу " + noga.name + " (" + noga.city_name + ")?";
    global.NogaTelegram.confirmAction(question, async function () {
      try {
        await global.NogaApi.deleteNoga(noga.id);
        await loadAndRender();
      } catch (err) {
        global.NogaTelegram.notify(err.message || "Ошибка удаления");
      }
    });
  }

  function bindForm() {
    var form = document.getElementById("nogaCreateForm");
    var openBtn = document.getElementById("btnAddNoga");
    var cancelBtn = document.getElementById("btnCancelNoga");
    var citySelect = document.getElementById("newNogaCity");

    if (openBtn) openBtn.hidden = !canManage();
    if (formBound) return;
    formBound = true;

    if (openBtn) {
      openBtn.addEventListener("click", function () {
        if (form) form.hidden = false;
      });
    }
    if (cancelBtn && form) {
      cancelBtn.addEventListener("click", function () {
        form.hidden = true;
      });
    }
    if (citySelect) {
      citySelect.addEventListener("change", toggleNewCityField);
    }

    bindTestSegmented();

    if (form) {
      form.addEventListener("submit", async function (e) {
        e.preventDefault();
        var name = document.getElementById("newNogaName").value;
        var cityValue = document.getElementById("newNogaCity").value;
        var cityName = document.getElementById("newNogaCityName").value;
        var isTest = document.getElementById("newNogaIsTest").value === "true";

        var payload = { name: name, is_test: isTest };
        if (cityValue && cityValue !== "__new__") {
          payload.city_id = Number(cityValue);
        } else {
          if (!cityName.trim()) {
            global.NogaTelegram.notify("Укажите город");
            return;
          }
          payload.city_name = cityName.trim();
        }

        try {
          await global.NogaApi.createNoga(payload);
          form.reset();
          form.hidden = true;
          resetSegmented();
          await loadCities();
          await loadAndRender();
        } catch (err) {
          global.NogaTelegram.notify(err.message || "Не удалось добавить ногу");
        }
      });
    }
  }

  function bindTestSegmented() {
    var buttons = document.querySelectorAll("#nogaTestSwitch .segmented__btn");
    var hidden = document.getElementById("newNogaIsTest");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        Array.prototype.forEach.call(buttons, function (b) {
          b.classList.remove("is-active");
          b.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("is-active");
        btn.setAttribute("aria-pressed", "true");
        if (hidden) hidden.value = btn.getAttribute("data-value");
      });
    });
  }

  function resetSegmented() {
    var buttons = document.querySelectorAll("#nogaTestSwitch .segmented__btn");
    var hidden = document.getElementById("newNogaIsTest");
    Array.prototype.forEach.call(buttons, function (b) {
      var isDefault = b.getAttribute("data-value") === "false";
      b.classList.toggle("is-active", isDefault);
      b.setAttribute("aria-pressed", isDefault ? "true" : "false");
    });
    if (hidden) hidden.value = "false";
  }

  function show() {
    global.NogaViews.show("viewNogas");
    bindForm();
    loadCities();
    loadAndRender();
  }

  function hide() {
    global.NogaViews.show("viewHome");
  }

  global.NogaNogas = { show: show, hide: hide, reload: loadAndRender };
})(window);
