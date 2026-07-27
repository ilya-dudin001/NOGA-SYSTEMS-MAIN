(function (global) {
  "use strict";

  var razgruzy = [];
  var nogas = [];
  var editingId = null;
  var openDetailId = null;
  var formBound = false;

  function canManage() {
    return global.NogaRoles.can("cities:manage");
  }

  function canSeeRazgruzy() {
    return global.NogaRoles.can("razgruz:read");
  }

  function canManageNogas() {
    return global.NogaRoles.can("nogas:manage");
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  /* Иконки в стиле остальных: контурные, 24×24, цвет наследуется от кнопки. */
  var ICONS = {
    detail: '<path d="m6 9 6 6 6-6"/>',
    edit: '<path d="M12 20h9"/><path d="M16.4 3.6a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    remove:
      '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="m19 6-1 14H6L5 6"/>' +
      '<path d="M10 11v6M14 11v6"/>',
  };

  function makeIconBtn(icon, label, onClick, extraClass) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn-icon" + (extraClass ? " " + extraClass : "");
    b.title = label;
    b.setAttribute("aria-label", label);
    b.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      ICONS[icon] +
      "</svg>";
    b.addEventListener("click", onClick);
    return b;
  }

  function setDetailBtnState(button, open) {
    if (!button) return;
    var label = open ? "Свернуть" : "Подробнее";
    button.classList.toggle("is-open", open);
    button.title = label;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-expanded", open ? "true" : "false");
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

    var detailBtn = makeIconBtn("detail", "Подробнее", function () {
      toggleDetail(city, detailWrap, detailBtn);
    });
    actions.appendChild(detailBtn);
    if (canManage()) {
      actions.appendChild(
        makeIconBtn("edit", "Изменить", function () {
          openForm(city);
        })
      );
      actions.appendChild(
        makeIconBtn(
          "remove",
          "Удалить",
          function () {
            removeCity(city);
          },
          "btn-icon--danger"
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
      setDetailBtnState(button, false);
      return;
    }

    openDetailId = city.id;
    container.hidden = false;
    container.innerHTML = "";
    container.appendChild(el("p", "empty-hint", "Загрузка…"));
    setDetailBtnState(button, true);

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

  /** Имена ног города: нужны, чтобы спросить про открепление до удаления. */
  async function attachedNogaNames(city) {
    if (!city.nogas_count) return [];
    try {
      var detail = await global.NogaApi.getCity(city.id);
      return (detail.nogas || []).map(function (noga) {
        return noga.name;
      });
    } catch (err) {
      return [];
    }
  }

  function nogasQuestion(city, names) {
    var shown = names.slice(0, 5).join(", ");
    if (names.length > 5) shown += " и ещё " + (names.length - 5);
    var head =
      names.length === 1
        ? "К городу " + city.name + " прикреплена нога: "
        : "К городу " + city.name + " прикреплены ноги: ";
    return (
      head +
      shown +
      ". В случае удаления города ноги автоматически с него снимутся. Удалить город?"
    );
  }

  async function removeCity(city) {
    var names = await attachedNogaNames(city);
    var question = names.length
      ? nogasQuestion(city, names)
      : "Удалить город " + city.name + "?";
    global.NogaTelegram.confirmAction(question, function () {
      performDelete(city, names.length > 0);
    });
  }

  async function performDelete(city, detachNogas) {
    try {
      await global.NogaApi.deleteCity(city.id, { detachNogas: detachNogas });
      if (openDetailId === city.id) openDetailId = null;
      // Ноги города стали неприкреплёнными — чек-лист в форме должен это знать.
      await loadNogas();
      await loadAndRender();
      await refreshDashboard();
    } catch (err) {
      // Ногу могли прикрепить, пока мы спрашивали — тогда сервер просит подтверждение.
      if (err.code === "CITY_HAS_NOGAS" && !detachNogas) {
        var names = (err.body && err.body.detail && err.body.detail.nogas) || [];
        global.NogaTelegram.confirmAction(
          names.length ? nogasQuestion(city, names) : err.message + ". Удалить город?",
          function () {
            performDelete(city, true);
          }
        );
        return;
      }
      global.NogaTelegram.notify(err.message || "Ошибка удаления");
    }
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
    return checkedIds("cityRazgruzy");
  }

  function checkedIds(boxId) {
    var box = document.getElementById(boxId);
    if (!box) return [];
    var ids = [];
    Array.prototype.forEach.call(box.querySelectorAll("input[type=checkbox]"), function (input) {
      if (input.checked) ids.push(Number(input.value));
    });
    return ids;
  }

  async function loadNogas() {
    if (!canManageNogas()) {
      nogas = [];
      return;
    }
    try {
      nogas = await global.NogaApi.listNogas();
    } catch (err) {
      nogas = [];
    }
  }

  /** Отмеченные ноги работают в этом городе, снятые — открепляются. */
  function fillNogaChecklist(cityId) {
    var field = document.getElementById("cityNogasField");
    var box = document.getElementById("cityNogas");
    if (!field || !box) return;
    field.hidden = !canManageNogas();
    box.innerHTML = "";

    if (!nogas.length) {
      box.appendChild(el("p", "detail__empty", "Ног пока нет — добавьте их на экране «Ноги»"));
      return;
    }

    nogas.forEach(function (noga) {
      var row = el("label", "checklist__row");
      var input = document.createElement("input");
      input.type = "checkbox";
      input.value = String(noga.id);
      input.checked = cityId !== null && noga.city_id === cityId;
      row.appendChild(input);

      var notes = [];
      if (noga.city_id === null || noga.city_id === undefined) {
        notes.push("без города");
      } else if (noga.city_id !== cityId) {
        notes.push("сейчас в " + noga.city_name);
      }
      if (noga.is_test) notes.push("тестовая");
      if (!noga.is_active) notes.push("выключена");

      row.appendChild(
        el(
          "span",
          "checklist__label",
          noga.name + (notes.length ? " · " + notes.join(", ") : "")
        )
      );
      box.appendChild(row);
    });
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
    fillNogaChecklist(city ? city.id : null);

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
    if (canManageNogas()) payload.noga_ids = checkedIds("cityNogas");
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
        // Состав города мог поменяться — перечитываем ноги, чтобы чек-лист
        // в следующий раз показал актуальную привязку.
        await loadNogas();
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
    await loadNogas();
    await loadAndRender();
  }

  function hide() {
    global.NogaViews.show("viewHome");
  }

  global.NogaCities = { show: show, hide: hide, reload: loadAndRender };
})(window);
