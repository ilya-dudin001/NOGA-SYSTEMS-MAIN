/* Трубки: список, двухшаговое создание и поэтапная карточка операции. */
(function (global) {
  "use strict";

  var cities = [];
  var cityCache = {};
  var formBound = false;
  var detailBound = false;
  var statusFilter = "";
  var detailId = null;
  var detailData = null;
  var detailBack = null;
  var wizardStep = 1;
  var objectUrls = [];
  var recalculationDraft = "";
  var usdtDraft = "";

  function canManage() {
    return global.NogaRoles.can("operations:all");
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function icon(name, title) {
    var node = el("span");
    node.setAttribute("data-em-icon", name);
    if (title) node.setAttribute("data-em-title", title);
    return node;
  }

  function hydrate(root) {
    if (global.EmIcons) global.EmIcons.hydrate(root);
    if (global.EmDS) global.EmDS.init(root);
  }

  function releaseBlobs() {
    objectUrls.forEach(function (url) {
      URL.revokeObjectURL(url);
    });
    objectUrls = [];
  }

  function statusInfo(value) {
    return global.NogaDict.trubkaStatus(value);
  }

  function statusPill(value) {
    var info = statusInfo(value);
    var pill = el("span", "em-pill " + info.cls, info.label);
    pill.insertBefore(icon(value === "vyplacheno" ? "check-circle" : "clock"), pill.firstChild);
    return pill;
  }

  function operationNumber(id) {
    var value = String(id);
    while (value.length < 6) value = "0" + value;
    return "EM-" + value;
  }

  /* ---------- таблицы ---------- */

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
      row.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          open();
        }
      });
      body.appendChild(row);
    });
    table.appendChild(body);
    scroll.appendChild(table);
    hydrate(scroll);
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

  async function renderDashboard() {
    var host = document.getElementById("dashTrubki");
    if (!host) return;
    host.innerHTML = "";
    host.appendChild(el("p", "empty-hint", "Загрузка…"));
    try {
      renderTable(host, await global.NogaApi.listTrubki({ limit: 8 }), "Трубок пока нет");
    } catch (err) {
      renderTable(host, [], "Не удалось загрузить трубки");
    }
  }

  function applyTotal(total) {
    var target = document.getElementById("trubkiTotal");
    if (target) target.textContent = global.NogaDict.formatNumber(total || 0);
  }

  function renderFilters() {
    var bar = document.getElementById("trubkiFilters");
    if (!bar) return;
    bar.innerHTML = "";
    [{ value: "", label: "Все" }].concat(global.NogaDict.TRUBKA_STATUSES).forEach(
      function (option) {
        var button = el("button", "tabs__btn", option.label);
        button.type = "button";
        button.setAttribute("role", "tab");
        var active = statusFilter === option.value;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
        button.addEventListener("click", function () {
          statusFilter = option.value;
          renderFilters();
          loadAndRender();
        });
        bar.appendChild(button);
      }
    );
  }

  async function loadAndRender() {
    var host = document.getElementById("trubkiList");
    if (!host) return;
    host.innerHTML = "";
    host.appendChild(el("p", "empty-hint", "Загрузка…"));
    try {
      renderTable(
        host,
        await global.NogaApi.listTrubki({ status: statusFilter }),
        statusFilter ? "Трубок с таким статусом нет" : "Трубок пока нет"
      );
    } catch (err) {
      renderTable(host, [], "Не удалось загрузить трубки");
    }
  }

  /* ---------- детали ---------- */

  function findFile(trubka, kind) {
    var files = trubka.files || [];
    for (var i = 0; i < files.length; i++) {
      if (files[i].kind === kind) return files[i];
    }
    return null;
  }

  function amountText(value, currency) {
    if (value === null || value === undefined || value === "") return "—";
    return global.NogaDict.formatAmount(value, currency || "RUB");
  }

  function moneyRow(label, value, iconName, modifier) {
    var row = el("div", "em-money__row" + (modifier ? " " + modifier : ""));
    var copy = el("div");
    copy.appendChild(el("div", "em-money__label", label));
    copy.appendChild(el("div", "em-money__value em-num", value));
    row.appendChild(copy);
    var badge = el("span", "em-icon-badge em-icon-badge--round");
    badge.appendChild(icon(iconName, label));
    row.appendChild(badge);
    return row;
  }

  function updateCalculation(input, payout, remainder, currency) {
    var raw = input.value.replace(",", ".");
    var amount = raw === "" ? null : Number(raw);
    if (amount === null || !isFinite(amount) || amount < 0) {
      payout.textContent = "—";
      remainder.textContent = "—";
      return;
    }
    payout.textContent = amountText(Math.round(amount * 0.1), currency);
    remainder.textContent = amountText(amount - Math.round(amount * 0.1), currency);
  }

  function editableMoney(trubka) {
    var money = el("div", "em-money");
    var first = el("div", "em-money__row");
    var field = el("div", "em-field");
    field.appendChild(el("label", "em-money__label", "Пересчёт"));
    var input = el("input", "em-trubka-money-input em-num");
    input.type = "number";
    input.min = "0";
    input.step = "1";
    input.inputMode = "numeric";
    input.placeholder = "Введите сумму";
    input.disabled = !canManage() || trubka.recalculation_amount !== null;
    input.value =
      recalculationDraft !== ""
        ? recalculationDraft
        : trubka.recalculation_amount === null
          ? ""
          : trubka.recalculation_amount;
    field.appendChild(input);
    first.appendChild(field);
    var badge = el("span", "em-icon-badge");
    badge.appendChild(icon("doc", "Сумма пересчёта"));
    first.appendChild(badge);
    money.appendChild(first);

    var payoutRow = moneyRow(
      "Нога 10%",
      amountText(trubka.noga_payout, trubka.amount_currency),
      "arrow-down-circle",
      "em-money__row--accent"
    );
    var remainderRow = moneyRow(
      "Остаток",
      amountText(trubka.remainder, trubka.amount_currency),
      "check-circle"
    );
    money.appendChild(payoutRow);
    money.appendChild(remainderRow);
    var payout = payoutRow.querySelector(".em-money__value");
    var remainder = remainderRow.querySelector(".em-money__value");
    if (input.value !== "") updateCalculation(input, payout, remainder, trubka.amount_currency);
    input.addEventListener("input", function () {
      recalculationDraft = input.value;
      updateCalculation(input, payout, remainder, trubka.amount_currency);
      updateActionState();
    });
    return money;
  }

  async function addStoredPreview(trubka, file, host) {
    try {
      var blob = await global.NogaApi.trubkaFileBlob(trubka.id, file.id);
      if (detailId !== trubka.id) return;
      var url = URL.createObjectURL(blob);
      objectUrls.push(url);
      var image = document.createElement("img");
      image.alt = file.kind === "money_photo" ? "Фото денег" : "Фото чека";
      image.src = url;
      image.addEventListener("error", function () {
        host.innerHTML = "";
        host.appendChild(icon("image", "Фото загружено, предпросмотр недоступен"));
        hydrate(host);
      });
      host.appendChild(image);
    } catch (err) {
      host.appendChild(icon("image", "Файл загружен"));
      hydrate(host);
    }
  }

  function photoField(trubka, kind, label) {
    var file = findFile(trubka, kind);
    var card = el("div", "em-card em-card--tight em-trubka-photo-card");
    var upload = el("div", "em-upload" + (file ? " is-done" : ""));
    if (file) {
      var preview = el("div", "em-upload__preview");
      upload.appendChild(preview);
      addStoredPreview(trubka, file, preview);
    } else if (canManage()) {
      var picker = el("label", "em-upload__btn");
      picker.appendChild(icon("camera"));
      var fileInput = el("input", "em-upload__drop");
      fileInput.type = "file";
      fileInput.accept = "image/*,.heic,.heif,.avif,.jfif";
      fileInput.setAttribute("aria-label", "Загрузить " + label.toLowerCase());
      picker.appendChild(fileInput);
      upload.appendChild(picker);
      fileInput.addEventListener("change", async function () {
        if (!fileInput.files || !fileInput.files[0]) return;
        picker.classList.add("is-loading");
        try {
          await global.NogaApi.uploadTrubkaFile(trubka.id, kind, fileInput.files[0]);
          await reloadDetail();
        } catch (err) {
          picker.classList.remove("is-loading");
          global.NogaTelegram.notify(err.message || "Не удалось загрузить фото");
        }
      });
    }
    var meta = el("div", "em-upload__meta");
    meta.appendChild(el("div", "em-upload__title", label));
    meta.appendChild(el("div", "em-upload__status", file ? "Добавлено" : "Не добавлено"));
    upload.appendChild(meta);
    card.appendChild(upload);
    return card;
  }

  function updateActionState() {
    var button = document.getElementById("trubkaStageAction");
    if (!button || !detailData) return;
    if (!canManage()) {
      button.disabled = true;
      return;
    }
    if (detailData.recalculation_amount === null) {
      button.disabled = !(Number(recalculationDraft) >= 0 && recalculationDraft !== "" && findFile(detailData, "money_photo"));
      return;
    }
    if (!detailData.report_sent_at) {
      var amount = usdtDraft !== "" ? Number(usdtDraft.replace(",", ".")) : detailData.usdt_received;
      button.disabled = !(amount >= 0 && findFile(detailData, "receipt_photo"));
    }
  }

  function stageSection(trubka) {
    var section = el("section", "em-trubka-detail__section");
    section.appendChild(editableMoney(trubka));
    section.appendChild(photoField(trubka, "money_photo", "Фото денег"));

    var action = el("button", "em-btn em-btn--primary em-btn--block em-trubka-action");
    action.id = "trubkaStageAction";
    action.type = "button";

    if (trubka.recalculation_amount === null) {
      action.textContent = "Пересчёт";
      action.addEventListener("click", async function () {
        action.disabled = true;
        action.classList.add("is-loading");
        try {
          await global.NogaApi.setTrubkaRecalculation(trubka.id, Number(recalculationDraft));
          recalculationDraft = "";
          await reloadDetail();
        } catch (err) {
          action.classList.remove("is-loading");
          global.NogaTelegram.notify(err.message || "Не удалось сохранить пересчёт");
          updateActionState();
        }
      });
    } else if (!trubka.report_sent_at) {
      var usdtField = el("div", "em-field em-trubka-detail__section");
      usdtField.appendChild(el("label", "em-label", "Зашло на счёт, USDT"));
      var control = el("div", "em-control em-control--amount");
      var usdt = el("input", "em-input em-num");
      usdt.type = "number";
      usdt.min = "0";
      usdt.step = "any";
      usdt.inputMode = "decimal";
      usdt.placeholder = "0,00";
      usdt.value = usdtDraft !== "" ? usdtDraft : trubka.usdt_received || "";
      usdt.disabled = !canManage();
      control.appendChild(usdt);
      control.appendChild(el("span", "em-currency", "USDT"));
      usdtField.appendChild(control);
      section.appendChild(usdtField);
      section.appendChild(photoField(trubka, "receipt_photo", "Фото чека"));

      if (canManage()) {
        usdt.addEventListener("input", function () {
          usdtDraft = usdt.value;
          updateActionState();
        });
        usdt.addEventListener("change", async function () {
          if (usdt.value === "" || Number(usdt.value) < 0) return;
          try {
            detailData = await global.NogaApi.setTrubkaUsdt(trubka.id, Number(usdt.value));
            usdtDraft = usdt.value;
            renderDetail(detailData);
          } catch (err) {
            global.NogaTelegram.notify(err.message || "Не удалось сохранить сумму USDT");
          }
        });
      }

      action.textContent = "Отправить отчёт";
      action.addEventListener("click", async function () {
        action.disabled = true;
        action.classList.add("is-loading");
        try {
          if (usdtDraft !== "" && Number(usdtDraft) !== Number(detailData.usdt_received)) {
            await global.NogaApi.setTrubkaUsdt(trubka.id, Number(usdtDraft));
          }
          await global.NogaApi.sendTrubkaReport(trubka.id);
          usdtDraft = "";
          await refreshDashboard();
          try {
            await loadAndRender();
          } catch (err) {
            /* список обновится при следующем заходе */
          }
          await reloadDetail();
          global.NogaTelegram.notify("Отчёт отправлен — трубка убрана из списка");
        } catch (err) {
          action.classList.remove("is-loading");
          global.NogaTelegram.notify(err.message || "Не удалось отправить отчёт");
          updateActionState();
        }
      });
    } else {
      action.textContent = "Отчёт отправлен";
      action.classList.add("is-success");
      action.disabled = true;
    }

    if (canManage() || trubka.report_sent_at) section.appendChild(action);
    return section;
  }

  function clientSection(trubka) {
    var details = el("details", "em-card em-card--flat em-trubka-client");
    var summary = el("summary", "em-trubka-client__summary");
    var summaryText = el("div");
    summaryText.appendChild(el("div", "em-card__title", "Данные клиента"));
    summaryText.appendChild(
      el(
        "div",
        "em-trubka-client__hint",
        trubka.customer_name || trubka.customer_address ? "Данные заполнены" : "Не заполнены"
      )
    );
    summary.appendChild(summaryText);
    summary.appendChild(icon("chevron-down"));
    details.appendChild(summary);

    var body = el("div", "em-trubka-client__body");
    function textField(label, value, multiline) {
      var field = el("div", "em-field");
      field.appendChild(el("label", "em-label", label));
      var control = el("div", "em-control");
      var input = el(multiline ? "textarea" : "input", "em-input");
      input.value = value || "";
      if (multiline) input.rows = 2;
      input.disabled = !canManage();
      control.appendChild(input);
      field.appendChild(control);
      body.appendChild(field);
      return input;
    }
    var customer = textField("ФИО", trubka.customer_name, false);
    var address = textField("Адрес", trubka.customer_address, true);
    var deliveryField = el("div", "em-field");
    deliveryField.appendChild(el("label", "em-label", "Способ передачи"));
    var deliveryControl = el("div", "em-control em-control--select");
    var delivery = el("select", "em-select");
    var empty = el("option", null, "Не выбран");
    empty.value = "";
    delivery.appendChild(empty);
    global.NogaDict.TRUBKA_DELIVERIES.forEach(function (item) {
      var option = el("option", null, item.label);
      option.value = item.value;
      delivery.appendChild(option);
    });
    delivery.value = trubka.delivery || "";
    delivery.disabled = !canManage();
    deliveryControl.appendChild(delivery);
    deliveryControl.appendChild(icon("chevron-down"));
    deliveryField.appendChild(deliveryControl);
    body.appendChild(deliveryField);

    if (canManage()) {
      var save = el("button", "em-btn em-btn--ghost em-btn--block em-trubka-client__actions", "Сохранить данные");
      save.type = "button";
      save.addEventListener("click", async function () {
        save.disabled = true;
        try {
          await global.NogaApi.updateTrubka(trubka.id, {
            customer_name: customer.value.trim() || null,
            customer_address: address.value.trim() || null,
            delivery: delivery.value || null,
          });
          await reloadDetail();
        } catch (err) {
          save.disabled = false;
          global.NogaTelegram.notify(err.message || "Не удалось сохранить данные");
        }
      });
      body.appendChild(save);
    }
    details.appendChild(body);
    return details;
  }

  function historyText(event) {
    var payload = event.payload || {};
    var labels = {
      created: "Создана трубка",
      money_photo_uploaded: "Загружено фото денег",
      receipt_photo_uploaded: "Загружено фото чека",
      report_sent: "Отчёт отправлен",
      updated: "Изменены данные трубки",
    };
    if (event.action === "recalculation_set") {
      return "Указан пересчёт: " + amountText(payload.amount, detailData.amount_currency);
    }
    if (event.action === "usdt_received_set") {
      return "Указана сумма захода: " + String(payload.amount).replace(".", ",") + " USDT";
    }
    if (event.action === "status_changed") {
      return "Сменён статус на «" + statusInfo(payload.to).label + "»";
    }
    return labels[event.action] || "Трубка изменена";
  }

  function historySection(trubka) {
    var section = el("section", "em-section em-trubka-history");
    var head = el("div", "em-trubka-history__head");
    head.appendChild(el("h3", "em-section__title", "История"));
    var toggle = el("button", "em-trubka-history__toggle", "Смотреть всё");
    toggle.type = "button";
    toggle.addEventListener("click", function () {
      section.classList.toggle("is-expanded");
      toggle.textContent = section.classList.contains("is-expanded") ? "Свернуть" : "Смотреть всё";
    });
    head.appendChild(toggle);
    section.appendChild(head);

    var timeline = el("div", "em-tl");
    (trubka.history || []).forEach(function (event, index) {
      var item = el("div", "em-tl__item");
      item.style.setProperty("--i", index);
      var date = new Date(event.created_at);
      item.appendChild(
        el(
          "div",
          "em-tl__time",
          isNaN(date.getTime())
            ? "—"
            : date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
        )
      );
      item.appendChild(el("div", "em-tl__text", historyText(event)));
      item.appendChild(
        el(
          "div",
          "em-trubka-history__details",
          (event.actor_name || "Система") + " · " + global.NogaDict.formatDateTime(event.created_at)
        )
      );
      timeline.appendChild(item);
    });
    if (!trubka.history || !trubka.history.length) {
      timeline.appendChild(el("div", "em-empty", "История пока пуста"));
    }
    section.appendChild(timeline);
    return section;
  }

  function renderDetail(trubka) {
    var body = document.getElementById("trubkaBody");
    if (!body) return;
    releaseBlobs();
    detailData = trubka;
    body.innerHTML = "";
    var root = el("article", "em-trubka-detail em-screen");

    var head = el("div", "em-trubka-detail__head");
    var title = el("div");
    title.appendChild(el("h2", "em-trubka-detail__title", operationNumber(trubka.id)));
    title.appendChild(el("p", "em-trubka-detail__number", "Трубка"));
    head.appendChild(title);

    if (canManage()) {
      var status = el("select", "em-trubka-detail__status-select");
      global.NogaDict.TRUBKA_MANUAL_STATUSES.forEach(function (item) {
        var option = el("option", null, item.label);
        option.value = item.value;
        status.appendChild(option);
      });
      if (trubka.status === "razgruzhaetsya") {
        var automatic = el("option", null, "Разгружается");
        automatic.value = "razgruzhaetsya";
        automatic.disabled = true;
        status.appendChild(automatic);
      }
      status.value = trubka.status;
      status.addEventListener("change", async function () {
        try {
          await global.NogaApi.updateTrubka(trubka.id, { status: status.value });
          await reloadDetail();
        } catch (err) {
          status.value = trubka.status;
          global.NogaTelegram.notify(err.message || "Не удалось изменить статус");
        }
      });
      head.appendChild(status);
    } else {
      head.appendChild(statusPill(trubka.status));
    }
    root.appendChild(head);

    var identity = el("div", "em-trubka-detail__identity");
    var city = el("div", "em-line");
    city.appendChild(icon("star"));
    city.appendChild(el("strong", null, trubka.city_name));
    identity.appendChild(city);
    var noga = el("div", "em-line");
    noga.appendChild(icon("profile"));
    noga.appendChild(el("strong", null, trubka.noga_name));
    identity.appendChild(noga);
    root.appendChild(identity);

    root.appendChild(stageSection(trubka));
    root.appendChild(clientSection(trubka));
    root.appendChild(historySection(trubka));

    if (canManage()) {
      var remove = el("button", "em-btn em-btn--danger em-btn--block em-trubka-danger", "Удалить трубку");
      remove.type = "button";
      remove.addEventListener("click", function () {
        removeTrubka(trubka);
      });
      root.appendChild(remove);
    }
    body.appendChild(root);
    hydrate(root);
    updateActionState();
  }

  async function reloadDetail() {
    if (detailId === null) return;
    detailData = await global.NogaApi.getTrubka(detailId);
    renderDetail(detailData);
  }

  async function openDetail(id, options) {
    bindDetail();
    detailId = id;
    detailData = null;
    detailBack = (options && options.back) || null;
    recalculationDraft = "";
    usdtDraft = "";
    global.NogaViews.show("viewTrubka");
    var body = document.getElementById("trubkaBody");
    body.innerHTML = "";
    body.appendChild(el("p", "empty-hint", "Загрузка…"));
    try {
      await reloadDetail();
    } catch (err) {
      body.innerHTML = "";
      body.appendChild(el("p", "empty-hint", "Не удалось загрузить трубку"));
    }
  }

  function leaveDetail() {
    detailId = null;
    detailData = null;
    releaseBlobs();
    var back = detailBack;
    detailBack = null;
    if (back === "stats" && global.NogaStats) {
      global.NogaStats.show();
      return;
    }
    if (back === "statsTrubki" && global.NogaStats) {
      global.NogaStats.showAllTrubki();
      return;
    }
    show();
  }

  function bindDetail() {
    if (detailBound) return;
    detailBound = true;
    var back = document.getElementById("trubkaBack");
    if (back) {
      back.addEventListener("click", leaveDetail);
    }
  }

  function removeTrubka(trubka) {
    global.NogaTelegram.confirmAction(
      "Удалить трубку " + operationNumber(trubka.id) + "?",
      async function () {
        try {
          await global.NogaApi.deleteTrubka(trubka.id);
          detailId = null;
          releaseBlobs();
          await show();
          await refreshDashboard();
        } catch (err) {
          global.NogaTelegram.notify(err.message || "Ошибка удаления");
        }
      }
    );
  }

  /* ---------- двухшаговое создание ---------- */

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
      var empty = el("option", null, placeholder);
      empty.value = "";
      select.appendChild(empty);
    }
    options.forEach(function (item) {
      var option = el("option", null, item.label);
      option.value = String(item.value);
      select.appendChild(option);
    });
    select.value = selected === null || selected === undefined ? "" : String(selected);
  }

  async function fillNogas(cityId) {
    var detail = await cityDetail(cityId);
    fillSelect(
      "trubkaNoga",
      ((detail && detail.nogas) || []).map(function (noga) {
        return {
          value: noga.id,
          label: noga.name + (noga.created_by_name ? " · " + noga.created_by_name : ""),
        };
      }),
      null,
      "Выберите ногу"
    );
  }

  function showWizardStep(step) {
    wizardStep = step;
    document.getElementById("trubkaStepOne").hidden = step !== 1;
    document.getElementById("trubkaStepTwo").hidden = step !== 2;
    document.getElementById("trubkaStepLabel").textContent = "Шаг " + step + " из 2";
    document.getElementById("btnTrubkaNext").hidden = step !== 1;
    document.getElementById("btnSaveTrubka").hidden = step !== 2;
    document.getElementById("btnCancelTrubka").textContent = step === 1 ? "Отмена" : "Назад";
    var dots = document.querySelectorAll(".em-trubka-wizard__dots span");
    Array.prototype.forEach.call(dots, function (dot, index) {
      dot.classList.toggle("is-active", index === step - 1);
    });
  }

  async function openForm() {
    var form = document.getElementById("trubkaForm");
    if (!form) return;
    if (!cities.length) await loadCities();
    fillSelect(
      "trubkaStatusField",
      global.NogaDict.TRUBKA_MANUAL_STATUSES.map(function (item) {
        return { value: item.value, label: item.label };
      }),
      "zacep"
    );
    fillSelect(
      "trubkaCity",
      cities.map(function (city) {
        return { value: city.id, label: city.name };
      }),
      null,
      "Выберите город"
    );
    fillSelect(
      "trubkaCurrency",
      global.NogaDict.CURRENCIES.map(function (currency) {
        return { value: currency.value, label: currency.short };
      }),
      "RUB"
    );
    fillSelect("trubkaNoga", [], null, "Сначала выберите город");
    document.getElementById("trubkaAmount").value = "";
    form.hidden = false;
    showWizardStep(1);
    hydrate(form);
    form.scrollIntoView({ block: "nearest" });
  }

  function closeForm() {
    var form = document.getElementById("trubkaForm");
    if (form) form.hidden = true;
    showWizardStep(1);
  }

  function setFieldError(controlId, state) {
    var control = document.getElementById(controlId);
    if (control && control.closest(".em-field")) {
      control.closest(".em-field").classList.toggle("is-error", state);
    }
  }

  async function refreshDashboard() {
    try {
      var summary = await global.NogaApi.dashboardSummary();
      global.NogaDashboard.applySummary(summary, { animate: false });
    } catch (err) {
      /* обновится при следующем входе */
    }
  }

  function bindForm() {
    var openButton = document.getElementById("btnAddTrubka");
    if (openButton) openButton.hidden = !canManage();
    if (formBound) return;
    formBound = true;

    if (openButton) openButton.addEventListener("click", openForm);
    document.getElementById("btnTrubkaNext").addEventListener("click", async function () {
      var cityId = document.getElementById("trubkaCity").value;
      setFieldError("trubkaCity", !cityId);
      if (!cityId) return;
      await fillNogas(Number(cityId));
      showWizardStep(2);
    });
    document.getElementById("btnCancelTrubka").addEventListener("click", function () {
      if (wizardStep === 2) showWizardStep(1);
      else closeForm();
    });
    document.getElementById("trubkaCity").addEventListener("change", function () {
      setFieldError("trubkaCity", false);
    });
    document.getElementById("trubkaAmount").addEventListener("input", function () {
      setFieldError("trubkaAmount", false);
    });
    document.getElementById("trubkaNoga").addEventListener("change", function () {
      setFieldError("trubkaNoga", false);
    });

    document.getElementById("trubkaForm").addEventListener("submit", async function (event) {
      event.preventDefault();
      var cityId = document.getElementById("trubkaCity").value;
      var nogaId = document.getElementById("trubkaNoga").value;
      var amount = document.getElementById("trubkaAmount").value;
      setFieldError("trubkaNoga", !nogaId);
      setFieldError("trubkaAmount", amount === "" || Number(amount) < 0);
      if (!cityId || !nogaId || amount === "" || Number(amount) < 0) return;

      var save = document.getElementById("btnSaveTrubka");
      save.disabled = true;
      save.classList.add("is-loading");
      try {
        var created = await global.NogaApi.createTrubka({
          status: document.getElementById("trubkaStatusField").value || "zacep",
          city_id: Number(cityId),
          noga_id: Number(nogaId),
          amount: Number(amount),
          amount_currency: document.getElementById("trubkaCurrency").value,
        });
        closeForm();
        await refreshDashboard();
        await openDetail(created.id);
      } catch (err) {
        global.NogaTelegram.notify(err.message || "Не удалось создать трубку");
      } finally {
        save.disabled = false;
        save.classList.remove("is-loading");
      }
    });
  }

  async function show(options) {
    global.NogaViews.show("viewTrubki");
    if (options && options.status !== undefined) statusFilter = options.status;
    cityCache = {};
    global.NogaNogas.release();
    bindForm();
    closeForm();
    renderFilters();
    await loadAndRender();
  }

  async function openCreate() {
    await show();
    await openForm();
  }

  function hide() {
    releaseBlobs();
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
