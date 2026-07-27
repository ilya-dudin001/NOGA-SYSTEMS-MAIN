(function (global) {
  "use strict";

  var razgruzy = [];
  var editingId = null;
  var openDetailId = null;
  var formBound = false;

  function canManage() {
    return global.NogaRoles.can("cities:manage");
  }

  function canSeeRazgruzy() {
    return global.NogaRoles.can("razgruz:read");
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function makeBtn(label, onClick, extraClass) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn-ghost" + (extraClass ? " " + extraClass : "");
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
  }

  /* ---------- список ---------- */

  async function loadAndRender() {
    var listEl = document.getElementById("citiesList");
    if (!listEl) return;
    listEl.innerHTML = '<p class="empty-hint">Загрузка…</p>';
    try {
      var cities = await global.NogaApi.listCities();
      renderList(cities);
    } catch (err) {
      listEl.innerHTML = "";
      listEl.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || err.code || "ошибка"))
      );
    }
  }

  function renderList(cities) {
    var listEl = document.getElementById("citiesList");
    listEl.innerHTML = "";
    if (!cities || !cities.length) {
      listEl.appendChild(el("p", "empty-hint", "Городов пока нет"));
      return;
    }
    cities.forEach(function (city) {
      listEl.appendChild(buildCard(city));
    });
  }

  function buildCard(city) {
    var status = global.NogaDict.cityStatus(city.status);
    var card = el("article", "user-card city-card");

    var top = el("div", "user-card__top");
    var head = el("div");
    head.appendChild(el("p", "user-card__name", city.name));

    var meta = "Запуск от: " + global.NogaDict.formatAmount(city.min_amount, city.min_amount_currency);
    meta += " · Ног: " + city.nogas_count;
    if (canSeeRazgruzy()) meta += " · Разгрузов: " + city.razgruzy.length;
    head.appendChild(el("p", "user-card__meta", meta));
    top.appendChild(head);
    top.appendChild(el("span", "status-pill " + status.cls, status.label));
    card.appendChild(top);

    if (canSeeRazgruzy() && city.razgruzy.length) {
      var chips = el("div", "chips");
      city.razgruzy.forEach(function (r) {
        chips.appendChild(
          el("span", "chip", r.name + " · " + global.NogaDict.formatPercent(r.commission_percent))
        );
      });
      card.appendChild(chips);
    }

    if (canManage()) {
      card.appendChild(buildStatusSwitch(city));
    }

    var actions = el("div", "user-card__actions");
    var detailWrap = el("div", "city-card__detail");
    detailWrap.hidden = true;

    var detailBtn = makeBtn("Подробнее", function () {
      toggleDetail(city, detailWrap, detailBtn);
    });
    actions.appendChild(detailBtn);
    if (canManage()) {
      actions.appendChild(
        makeBtn("Изменить", function () {
          openForm(city);
        })
      );
      actions.appendChild(
        makeBtn(
          "Удалить",
          function () {
            removeCity(city);
          },
          "btn-ghost--danger"
        )
      );
    }
    card.appendChild(actions);
    card.appendChild(detailWrap);

    // Карточки перерисовываются целиком после каждого изменения — раскрытый
    // блок деталей возвращаем на место, чтобы он не схлопывался под пользователем.
    if (openDetailId === city.id) {
      toggleDetail(city, detailWrap, detailBtn);
    }
    return card;
  }

  function buildStatusSwitch(city) {
    var wrap = el("div", "segmented segmented--triple");
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", "Статус города " + city.name);

    global.NogaDict.CITY_STATUSES.forEach(function (item) {
      var btn = el("button", "segmented__btn", item.short);
      btn.type = "button";
      var active = city.status === item.value;
      if (active) btn.classList.add("is-active");
      btn.setAttribute("aria-pressed", active ? "true" : "false");
      btn.addEventListener("click", function () {
        if (city.status === item.value) return;
        patch(city, { status: item.value });
      });
      wrap.appendChild(btn);
    });
    return wrap;
  }

  /* ---------- детали ---------- */

  async function toggleDetail(city, container, button) {
    if (!container.hidden) {
      container.hidden = true;
      container.innerHTML = "";
      openDetailId = null;
      if (button) button.textContent = "Подробнее";
      return;
    }

    openDetailId = city.id;
    container.hidden = false;
    container.innerHTML = "";
    container.appendChild(el("p", "empty-hint", "Загрузка…"));
    if (button) button.textContent = "Свернуть";

    try {
      var detail = await global.NogaApi.getCity(city.id);
      renderDetail(detail, container);
    } catch (err) {
      container.innerHTML = "";
      container.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || "ошибка"))
      );
    }
  }

  function renderDetail(city, container) {
    container.innerHTML = "";

    if (global.NogaRoles.can("nogas:read")) {
      container.appendChild(el("p", "detail__title", "Ноги (" + city.nogas.length + ")"));
      if (!city.nogas.length) {
        container.appendChild(el("p", "detail__empty", "Ног в городе пока нет"));
      } else {
        var nogasList = el("ul", "detail-list");
        city.nogas.forEach(function (noga) {
          var flags = [];
          if (noga.is_test) flags.push("тестовая");
          if (!noga.is_active) flags.push("выключена");
          if (!flags.length) flags.push("рабочая");
          var line = el("li", "detail-list__item");
          line.appendChild(el("span", "detail-list__name", noga.name));
          line.appendChild(
            el(
              "span",
              "detail-list__meta",
              flags.join(", ") +
                " · добавил " +
                (noga.created_by_name || "—") +
                " · " +
                global.NogaDict.formatDate(noga.created_at)
            )
          );
          nogasList.appendChild(line);
        });
        container.appendChild(nogasList);
      }
    }

    if (canSeeRazgruzy()) {
      container.appendChild(el("p", "detail__title", "Разгрузы (" + city.razgruzy.length + ")"));
      if (!city.razgruzy.length) {
        container.appendChild(el("p", "detail__empty", "Разгрузы не привязаны"));
      } else {
        var razgruzList = el("ul", "detail-list");
        city.razgruzy.forEach(function (r) {
          var line = el("li", "detail-list__item");
          line.appendChild(
            el(
              "span",
              "detail-list__name",
              r.name + " — " + global.NogaDict.formatPercent(r.commission_percent)
            )
          );
          line.appendChild(
            el(
              "span",
              "detail-list__meta",
              "успешно разгружено: " +
                r.completed_orders +
                " · добавил " +
                (r.created_by_name || "—") +
                " · " +
                global.NogaDict.formatDate(r.created_at) +
                (r.contact ? " · " + r.contact : "")
            )
          );
          razgruzList.appendChild(line);
        });
        container.appendChild(razgruzList);
      }
    }

    container.appendChild(el("p", "detail__title", "Последние заказы"));
    if (!city.recent_orders.length) {
      container.appendChild(
        el("p", "detail__empty", "Заказов пока нет — раздел операций ещё не запущен")
      );
    } else {
      var orders = el("ul", "detail-list");
      city.recent_orders.slice(0, 5).forEach(function (order) {
        var line = el("li", "detail-list__item");
        line.appendChild(el("span", "detail-list__name", order.title || "Заказ"));
        line.appendChild(
          el(
            "span",
            "detail-list__meta",
            "нога: " + (order.noga_name || "—") + " · разгруз: " + (order.razgruz_name || "—")
          )
        );
        orders.appendChild(line);
      });
      container.appendChild(orders);
    }
  }

  /* ---------- запись ---------- */

  async function patch(city, payload) {
    try {
      await global.NogaApi.updateCity(city.id, payload);
      await loadAndRender();
      await refreshDashboard();
    } catch (err) {
      global.NogaTelegram.notify(err.message || "Не удалось изменить город");
    }
  }

  function removeCity(city) {
    global.NogaTelegram.confirmAction("Удалить город " + city.name + "?", async function () {
      try {
        await global.NogaApi.deleteCity(city.id);
        if (openDetailId === city.id) openDetailId = null;
        await loadAndRender();
        await refreshDashboard();
      } catch (err) {
        global.NogaTelegram.notify(err.message || "Ошибка удаления");
      }
    });
  }

  async function refreshDashboard() {
    try {
      var summary = await global.NogaApi.dashboardSummary();
      global.NogaDashboard.applySummary(summary, { animate: false });
    } catch (e) {
      /* дашборд обновится при следующем входе */
    }
  }

  /* ---------- форма ---------- */

  function fillStatusSelect() {
    var select = document.getElementById("cityStatus");
    if (!select || select.options.length) return;
    global.NogaDict.CITY_STATUSES.forEach(function (item) {
      var opt = document.createElement("option");
      opt.value = item.value;
      opt.textContent = item.label;
      select.appendChild(opt);
    });
  }

  function fillCurrencySelect() {
    var select = document.getElementById("cityCurrency");
    if (!select || select.options.length) return;
    var empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "Не задана";
    select.appendChild(empty);
    global.NogaDict.CURRENCIES.forEach(function (item) {
      var opt = document.createElement("option");
      opt.value = item.value;
      opt.textContent = item.label + " (" + item.sign + ")";
      select.appendChild(opt);
    });
  }

  async function loadRazgruzy() {
    if (!canSeeRazgruzy()) {
      razgruzy = [];
      return;
    }
    try {
      razgruzy = await global.NogaApi.listRazgruzy();
    } catch (err) {
      razgruzy = [];
    }
  }

  function fillRazgruzChecklist(selectedIds) {
    var field = document.getElementById("cityRazgruzyField");
    var box = document.getElementById("cityRazgruzy");
    if (!field || !box) return;
    field.hidden = !canSeeRazgruzy();
    box.innerHTML = "";

    if (!razgruzy.length) {
      box.appendChild(
        el("p", "detail__empty", "Разгрузов пока нет — добавьте их на экране «Разгрузы»")
      );
      return;
    }

    razgruzy.forEach(function (r) {
      var row = el("label", "checklist__row");
      var input = document.createElement("input");
      input.type = "checkbox";
      input.value = String(r.id);
      input.checked = selectedIds.indexOf(r.id) !== -1;
      row.appendChild(input);
      row.appendChild(
        el(
          "span",
          "checklist__label",
          r.name +
            " · " +
            global.NogaDict.formatPercent(r.commission_percent) +
            (r.is_active ? "" : " · выключен")
        )
      );
      box.appendChild(row);
    });
  }

  function selectedRazgruzIds() {
    var box = document.getElementById("cityRazgruzy");
    if (!box) return [];
    var ids = [];
    Array.prototype.forEach.call(box.querySelectorAll("input[type=checkbox]"), function (input) {
      if (input.checked) ids.push(Number(input.value));
    });
    return ids;
  }

  function openForm(city) {
    var form = document.getElementById("cityForm");
    if (!form) return;
    fillStatusSelect();
    fillCurrencySelect();

    editingId = city ? city.id : null;
    document.getElementById("cityFormTitle").textContent = city
      ? "Изменить город"
      : "Новый город";
    document.getElementById("cityName").value = city ? city.name : "";
    document.getElementById("cityStatus").value = city ? city.status : "working";
    document.getElementById("cityMinAmount").value =
      city && city.min_amount !== null && city.min_amount !== undefined ? city.min_amount : "";
    document.getElementById("cityCurrency").value =
      city && city.min_amount_currency ? city.min_amount_currency : "";

    fillRazgruzChecklist(
      city && city.razgruzy
        ? city.razgruzy.map(function (r) {
            return r.id;
          })
        : []
    );

    form.hidden = false;
    form.scrollIntoView({ block: "nearest" });
  }

  function closeForm() {
    var form = document.getElementById("cityForm");
    if (form) form.hidden = true;
    editingId = null;
  }

  function collectPayload() {
    var name = document.getElementById("cityName").value.trim();
    if (!name) {
      global.NogaTelegram.notify("Укажите название города");
      return null;
    }

    var rawAmount = document.getElementById("cityMinAmount").value.trim();
    var currency = document.getElementById("cityCurrency").value;
    if (rawAmount && !currency) {
      global.NogaTelegram.notify("Выберите валюту для суммы запуска");
      return null;
    }

    var payload = {
      name: name,
      status: document.getElementById("cityStatus").value,
      min_amount: rawAmount ? Number(rawAmount) : null,
      min_amount_currency: rawAmount ? currency : null,
    };
    if (canSeeRazgruzy()) payload.razgruz_ids = selectedRazgruzIds();
    return payload;
  }

  function bindForm() {
    var openBtn = document.getElementById("btnAddCity");
    if (openBtn) openBtn.hidden = !canManage();
    if (formBound) return;
    formBound = true;

    if (openBtn) {
      openBtn.addEventListener("click", function () {
        openForm(null);
      });
    }
    var cancelBtn = document.getElementById("btnCancelCity");
    if (cancelBtn) cancelBtn.addEventListener("click", closeForm);

    var form = document.getElementById("cityForm");
    if (!form) return;
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var payload = collectPayload();
      if (!payload) return;
      try {
        if (editingId === null) {
          await global.NogaApi.createCity(payload);
        } else {
          await global.NogaApi.updateCity(editingId, payload);
        }
        closeForm();
        await loadAndRender();
        await refreshDashboard();
      } catch (err) {
        global.NogaTelegram.notify(err.message || "Не удалось сохранить город");
      }
    });
  }

  async function show() {
    global.NogaViews.show("viewCities");
    bindForm();
    closeForm();
    await loadRazgruzy();
    await loadAndRender();
  }

  function hide() {
    global.NogaViews.show("viewHome");
  }

  global.NogaCities = { show: show, hide: hide, reload: loadAndRender };
})(window);
