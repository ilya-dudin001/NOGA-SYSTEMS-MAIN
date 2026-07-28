/* Трубки (заказы): таблица на дашборде, экран списка, детали с картой и форма. */
(function (global) {
  "use strict";

  var cities = [];
  // city_id → детали города: ноги в нём и разгрузы. Нужны только форме.
  var cityCache = {};
  var editingId = null;
  var formBound = false;
  var detailBound = false;
  var statusFilter = "";
  // Куда возвращаться после сохранения: в список или в открытые детали.
  var returnToDetail = false;
  var detailId = null;

  function canManage() {
    return global.NogaRoles.can("operations:all");
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

  function statusPill(value, extraClass) {
    var status = global.NogaDict.trubkaStatus(value);
    return el(
      "span",
      "trubka-status " + status.cls + (extraClass ? " " + extraClass : ""),
      status.label
    );
  }

  /* ---------- таблица ---------- */

  var COLUMNS = ["Статус", "Город", "Сумма", "Нога", "Чья нога"];

  function buildTable(items) {
    var scroll = el("div", "table-scroll");
    var table = el("table", "trubki-table");

    var head = el("thead");
    var headRow = el("tr");
    COLUMNS.forEach(function (name) {
      headRow.appendChild(el("th", null, name));
    });
    head.appendChild(headRow);
    table.appendChild(head);

    var body = el("tbody");
    items.forEach(function (trubka) {
      var row = el("tr", "trubki-table__row");
      row.tabIndex = 0;
      row.setAttribute("role", "button");

      var statusCell = el("td");
      statusCell.appendChild(statusPill(trubka.status));
      row.appendChild(statusCell);

      row.appendChild(el("td", null, trubka.city_name));
      row.appendChild(
        el(
          "td",
          "trubki-table__amount",
          global.NogaDict.formatCompactAmount(trubka.amount, trubka.amount_currency)
        )
      );
      row.appendChild(el("td", null, trubka.noga_name));
      row.appendChild(el("td", "trubki-table__owner", trubka.noga_owner_name || "—"));

      function open() {
        openDetail(trubka.id);
      }
      row.addEventListener("click", open);
      row.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      });

      body.appendChild(row);
    });
    table.appendChild(body);
    scroll.appendChild(table);
    return scroll;
  }

  function renderTable(host, items, emptyText) {
    host.innerHTML = "";
    if (!items || !items.length) {
      host.appendChild(el("p", "empty-hint", emptyText));
      return;
    }
    host.appendChild(buildTable(items));
  }

  /* ---------- дашборд ---------- */

  /** Блок «Трубки» на главной: последние заказы и общий счётчик. */
  async function renderDashboard() {
    var host = document.getElementById("dashTrubki");
    if (!host) return;
    host.innerHTML = "";
    host.appendChild(el("p", "empty-hint", "Загрузка…"));
    try {
      var items = await global.NogaApi.listTrubki({ limit: 8 });
      renderTable(host, items, "Трубок пока нет");
    } catch (err) {
      host.innerHTML = "";
      host.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || err.code || "ошибка"))
      );
    }
  }

  function applyTotal(total) {
    var el2 = document.getElementById("trubkiTotal");
    if (el2) el2.textContent = global.NogaDict.formatNumber(total || 0);
  }

  /* ---------- список ---------- */

  function renderFilters() {
    var bar = document.getElementById("trubkiFilters");
    if (!bar) return;
    bar.innerHTML = "";
    var options = [{ value: "", label: "Все" }].concat(global.NogaDict.TRUBKA_STATUSES);
    options.forEach(function (option) {
      var btn = el("button", "tabs__btn", option.label);
      btn.type = "button";
      btn.setAttribute("role", "tab");
      var active = statusFilter === option.value;
      if (active) btn.classList.add("is-active");
      btn.setAttribute("aria-selected", active ? "true" : "false");
      btn.addEventListener("click", function () {
        statusFilter = option.value;
        renderFilters();
        loadAndRender();
      });
      bar.appendChild(btn);
    });
  }

  async function loadAndRender() {
    var listEl = document.getElementById("trubkiList");
    if (!listEl) return;
    listEl.innerHTML = "";
    listEl.appendChild(el("p", "empty-hint", "Загрузка…"));
    try {
      var items = await global.NogaApi.listTrubki({ status: statusFilter });
      renderTable(
        listEl,
        items,
        statusFilter ? "Трубок с таким статусом нет" : "Трубок пока нет"
      );
    } catch (err) {
      listEl.innerHTML = "";
      listEl.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || err.code || "ошибка"))
      );
    }
  }

  /* ---------- детали ---------- */

  function detailRow(list, name, value, extraClass) {
    var item = el("li", "detail-list__item" + (extraClass ? " " + extraClass : ""));
    item.appendChild(el("span", "detail-list__name", name));
    item.appendChild(el("span", "detail-list__meta", value));
    list.appendChild(item);
    return item;
  }

  /** Карта без ключа: обычный embed Google по строке адреса. */
  function mapSection(address) {
    var section = el("section", "map-block");
    section.appendChild(el("p", "detail__title", "Адрес на карте"));

    var frame = document.createElement("iframe");
    frame.className = "map-block__frame";
    frame.loading = "lazy";
    frame.referrerPolicy = "no-referrer-when-downgrade";
    frame.title = "Карта: " + address;
    frame.src =
      "https://maps.google.com/maps?q=" +
      encodeURIComponent(address) +
      "&z=16&hl=ru&output=embed";
    section.appendChild(frame);

    var link = el("a", "btn-all", "Открыть в Google Картах");
    link.href =
      "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(address);
    link.target = "_blank";
    link.rel = "noopener";
    section.appendChild(link);
    return section;
  }

  function renderDetail(trubka) {
    var body = document.getElementById("trubkaBody");
    if (!body) return;
    body.innerHTML = "";

    var head = el("section", "trubka-head");
    head.appendChild(statusPill(trubka.status, "trubka-status--lg"));
    head.appendChild(
      el(
        "p",
        "trubka-head__amount",
        global.NogaDict.formatAmount(trubka.amount, trubka.amount_currency)
      )
    );
    head.appendChild(el("p", "trubka-head__city", trubka.city_name));
    body.appendChild(head);

    var main = el("ul", "detail-list");
    detailRow(main, "Город", trubka.city_name);
    detailRow(main, "Сумма", global.NogaDict.formatAmount(trubka.amount, trubka.amount_currency));
    detailRow(main, "Нога", trubka.noga_name);
    detailRow(main, "Чья нога", trubka.noga_owner_name || "—");
    if (global.NogaRoles.can("razgruz:read")) {
      detailRow(main, "Разгруз", trubka.razgruz_name || "не выбран");
    }
    detailRow(main, "Завёл", trubka.created_by_name || "—");
    detailRow(main, "Создана", global.NogaDict.formatDateTime(trubka.created_at));
    body.appendChild(main);

    body.appendChild(el("p", "detail__title", "Заказчик"));
    var customer = el("ul", "detail-list");
    detailRow(customer, "ФИО", trubka.customer_name);
    detailRow(customer, "Адрес", trubka.customer_address);
    detailRow(customer, "Как забрали", global.NogaDict.trubkaDelivery(trubka.delivery).label);
    body.appendChild(customer);

    body.appendChild(mapSection(trubka.customer_address));

    if (global.NogaRoles.can("nogas:read")) {
      body.appendChild(el("p", "detail__title", "Нога: " + trubka.noga_name));
      var nogaBox = el("div", "detail-list__panel");
      body.appendChild(nogaBox);
      global.NogaNogas.renderCard(trubka.noga_id, nogaBox);
    }

    if (canManage()) {
      var actions = el("div", "user-card__actions");
      actions.appendChild(
        makeBtn(
          "Удалить трубку",
          function () {
            removeTrubka(trubka);
          },
          "btn-ghost--danger"
        )
      );
      body.appendChild(actions);
    }
  }

  async function openDetail(id) {
    bindDetail();
    detailId = id;
    global.NogaViews.show("viewTrubka");

    var body = document.getElementById("trubkaBody");
    var editBtn = document.getElementById("btnEditTrubka");
    if (editBtn) editBtn.hidden = true;
    if (body) {
      body.innerHTML = "";
      body.appendChild(el("p", "empty-hint", "Загрузка…"));
    }

    try {
      var trubka = await global.NogaApi.getTrubka(id);
      renderDetail(trubka);
      if (editBtn) editBtn.hidden = !canManage();
    } catch (err) {
      if (!body) return;
      body.innerHTML = "";
      body.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || "ошибка"))
      );
    }
  }

  function bindDetail() {
    if (detailBound) return;
    detailBound = true;

    var back = document.getElementById("trubkaBack");
    if (back) {
      back.addEventListener("click", function () {
        detailId = null;
        show();
      });
    }

    var editBtn = document.getElementById("btnEditTrubka");
    if (editBtn) {
      editBtn.addEventListener("click", async function () {
        if (detailId === null) return;
        try {
          var trubka = await global.NogaApi.getTrubka(detailId);
          await show();
          await openForm(trubka, { fromDetail: true });
        } catch (err) {
          global.NogaTelegram.notify(err.message || "Не удалось открыть форму");
        }
      });
    }
  }

  function removeTrubka(trubka) {
    global.NogaTelegram.confirmAction(
      "Удалить трубку по городу " + trubka.city_name + "?",
      async function () {
        try {
          await global.NogaApi.deleteTrubka(trubka.id);
          detailId = null;
          await show();
          await refreshDashboard();
        } catch (err) {
          global.NogaTelegram.notify(err.message || "Ошибка удаления");
        }
      }
    );
  }

  /* ---------- форма ---------- */

  /** Свои города плюс витрина работающих: трубку заводят и в чужом городе. */
  async function loadCities() {
    try {
      var lists = await Promise.all([
        global.NogaApi.listCities("own"),
        global.NogaApi.listCities("working"),
      ]);
      var seen = {};
      cities = [];
      lists[0].concat(lists[1]).forEach(function (city) {
        if (seen[city.id]) return;
        seen[city.id] = true;
        cities.push(city);
      });
      cities.sort(function (a, b) {
        return a.name.localeCompare(b.name, "ru");
      });
    } catch (err) {
      cities = [];
    }
  }

  /** Ноги и разгрузы города приходят только в его карточке — она же и кэшируется. */
  async function cityDetail(cityId) {
    if (!cityId) return null;
    if (cityCache[cityId]) return cityCache[cityId];
    try {
      cityCache[cityId] = await global.NogaApi.getCity(cityId);
    } catch (err) {
      cityCache[cityId] = null;
    }
    return cityCache[cityId];
  }

  function fillSelect(id, options, selected, placeholder) {
    var select = document.getElementById(id);
    if (!select) return;
    select.innerHTML = "";
    if (placeholder) {
      var empty = document.createElement("option");
      empty.value = "";
      empty.textContent = placeholder;
      select.appendChild(empty);
    }
    options.forEach(function (option) {
      var node = document.createElement("option");
      node.value = String(option.value);
      node.textContent = option.label;
      select.appendChild(node);
    });
    select.value =
      selected === null || selected === undefined ? "" : String(selected);
  }

  function fillStatusSelect(selected) {
    fillSelect(
      "trubkaStatusField",
      global.NogaDict.TRUBKA_STATUSES.map(function (s) {
        return { value: s.value, label: s.label };
      }),
      selected || "zacep"
    );
  }

  function fillCurrencySelect(selected) {
    fillSelect(
      "trubkaCurrency",
      global.NogaDict.CURRENCIES.map(function (c) {
        return { value: c.value, label: c.label };
      }),
      selected || "RUB"
    );
  }

  function fillCitySelect(selected) {
    fillSelect(
      "trubkaCity",
      cities.map(function (city) {
        var status = global.NogaDict.cityStatus(city.status);
        return {
          value: city.id,
          label: city.status === "working" ? city.name : city.name + " (" + status.short + ")",
        };
      }),
      selected,
      "Выберите город"
    );
  }

  /**
   * Ноги и разгрузы зависят от города: в списке ног стоят все ноги города,
   * включая чужие — «чья нога» именно поэтому и различается.
   */
  async function fillCityDependent(cityId, trubka) {
    var detail = await cityDetail(cityId);
    var nogas = (detail && detail.nogas) || [];
    var options = nogas.map(function (noga) {
      var owner = noga.created_by_name ? " · " + noga.created_by_name : "";
      return { value: noga.id, label: noga.name + owner };
    });
    // Ногу могли перевести в другой город — не теряем её из формы правки.
    var known = nogas.some(function (noga) {
      return trubka && noga.id === trubka.noga_id;
    });
    if (trubka && trubka.noga_id && !known) {
      options.unshift({ value: trubka.noga_id, label: trubka.noga_name + " (не в этом городе)" });
    }
    fillSelect("trubkaNoga", options, trubka ? trubka.noga_id : null, "Выберите ногу");

    var razgruzField = document.getElementById("trubkaRazgruz");
    var razgruzy = (detail && detail.razgruzy) || [];
    fillSelect(
      "trubkaRazgruz",
      razgruzy.map(function (r) {
        return { value: r.id, label: r.name + " · " + global.NogaDict.formatPercent(r.commission_percent) };
      }),
      trubka ? trubka.razgruz_id : null,
      "Не выбран"
    );
    if (razgruzField) {
      razgruzField.closest(".field").hidden = !global.NogaRoles.can("razgruz:read");
    }
  }

  function setDeliverySwitch(value) {
    var buttons = document.querySelectorAll("#trubkaDeliverySwitch .segmented__btn");
    var hidden = document.getElementById("trubkaDelivery");
    Array.prototype.forEach.call(buttons, function (btn) {
      var active = btn.getAttribute("data-value") === value;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (hidden) hidden.value = value;
  }

  async function openForm(trubka, options) {
    var form = document.getElementById("trubkaForm");
    if (!form) return;

    editingId = trubka ? trubka.id : null;
    returnToDetail = Boolean(options && options.fromDetail);
    document.getElementById("trubkaFormTitle").textContent = trubka
      ? "Изменить трубку"
      : "Новая трубка";

    if (!cities.length) await loadCities();
    fillStatusSelect(trubka ? trubka.status : "zacep");
    fillCurrencySelect(trubka ? trubka.amount_currency : "RUB");
    fillCitySelect(trubka ? trubka.city_id : null);
    await fillCityDependent(trubka ? trubka.city_id : null, trubka);

    document.getElementById("trubkaAmount").value = trubka ? trubka.amount : "";
    document.getElementById("trubkaCustomer").value = trubka ? trubka.customer_name : "";
    document.getElementById("trubkaAddress").value = trubka ? trubka.customer_address : "";
    setDeliverySwitch(trubka ? trubka.delivery : "zahod");

    form.hidden = false;
    form.scrollIntoView({ block: "nearest" });
  }

  function closeForm() {
    var form = document.getElementById("trubkaForm");
    if (form) form.hidden = true;
    editingId = null;
    returnToDetail = false;
  }

  function collectPayload() {
    var cityId = document.getElementById("trubkaCity").value;
    if (!cityId) {
      global.NogaTelegram.notify("Выберите город");
      return null;
    }
    var nogaId = document.getElementById("trubkaNoga").value;
    if (!nogaId) {
      global.NogaTelegram.notify("Выберите ногу — в городе должна быть хотя бы одна");
      return null;
    }
    var rawAmount = document.getElementById("trubkaAmount").value.trim();
    if (!rawAmount || Number(rawAmount) < 0) {
      global.NogaTelegram.notify("Укажите сумму трубки");
      return null;
    }
    var customer = document.getElementById("trubkaCustomer").value.trim();
    if (!customer) {
      global.NogaTelegram.notify("Укажите ФИО заказчика");
      return null;
    }
    var address = document.getElementById("trubkaAddress").value.trim();
    if (!address) {
      global.NogaTelegram.notify("Укажите адрес заказчика");
      return null;
    }

    var razgruzId = document.getElementById("trubkaRazgruz").value;
    return {
      status: document.getElementById("trubkaStatusField").value,
      city_id: Number(cityId),
      noga_id: Number(nogaId),
      razgruz_id: razgruzId ? Number(razgruzId) : null,
      amount: Number(rawAmount),
      amount_currency: document.getElementById("trubkaCurrency").value,
      customer_name: customer,
      customer_address: address,
      delivery: document.getElementById("trubkaDelivery").value,
    };
  }

  async function refreshDashboard() {
    try {
      var summary = await global.NogaApi.dashboardSummary();
      global.NogaDashboard.applySummary(summary, { animate: false });
    } catch (e) {
      /* дашборд обновится при следующем входе */
    }
  }

  function bindForm() {
    var openBtn = document.getElementById("btnAddTrubka");
    if (openBtn) openBtn.hidden = !canManage();
    if (formBound) return;
    formBound = true;

    if (openBtn) {
      openBtn.addEventListener("click", function () {
        openForm(null);
      });
    }
    var cancelBtn = document.getElementById("btnCancelTrubka");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        var backTo = returnToDetail ? editingId : null;
        closeForm();
        if (backTo) openDetail(backTo);
      });
    }

    var citySelect = document.getElementById("trubkaCity");
    if (citySelect) {
      citySelect.addEventListener("change", function () {
        fillCityDependent(citySelect.value ? Number(citySelect.value) : null, null);
      });
    }

    var buttons = document.querySelectorAll("#trubkaDeliverySwitch .segmented__btn");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        setDeliverySwitch(btn.getAttribute("data-value"));
      });
    });

    var form = document.getElementById("trubkaForm");
    if (!form) return;
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var payload = collectPayload();
      if (!payload) return;
      var savedId = editingId;
      var backToDetail = returnToDetail;
      try {
        if (savedId === null) {
          await global.NogaApi.createTrubka(payload);
        } else {
          await global.NogaApi.updateTrubka(savedId, payload);
        }
        closeForm();
        await refreshDashboard();
        if (backToDetail && savedId) {
          await openDetail(savedId);
          return;
        }
        await loadAndRender();
      } catch (err) {
        global.NogaTelegram.notify(err.message || "Не удалось сохранить трубку");
      }
    });
  }

  async function show(options) {
    global.NogaViews.show("viewTrubki");
    if (options && options.status !== undefined) statusFilter = options.status;
    // Состав города мог поменяться, пока пользователь ходил по другим экранам.
    cityCache = {};
    global.NogaNogas.release();
    bindForm();
    closeForm();
    renderFilters();
    await loadAndRender();
  }

  /** Вход из меню «+»: экран уже со открытой формой нового заказа. */
  async function openCreate() {
    await show();
    await openForm(null);
  }

  function hide() {
    global.NogaViews.show("viewHome");
  }

  global.NogaTrubki = {
    show: show,
    hide: hide,
    reload: loadAndRender,
    openCreate: openCreate,
    openDetail: openDetail,
    renderDashboard: renderDashboard,
    applyTotal: applyTotal,
  };
})(window);
