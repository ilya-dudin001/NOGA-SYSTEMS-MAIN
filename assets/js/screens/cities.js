(function (global) {
  "use strict";

  var razgruzy = [];
  var nogas = [];
  var editingId = null;
  var editingCity = null;
  var openDetailId = null;
  var formBound = false;
  // own — свой участок, working — общая витрина городов в работе.
  var mode = "own";
  var suggestTimer = null;
  var suggestSeq = 0;
  var suggestItems = [];
  var suggestActive = -1;
  var currencyTouched = false;

  function canManage() {
    return global.NogaRoles.can("cities:manage");
  }

  function seesAllCities() {
    return global.NogaRoles.can("cities:all");
  }

  /** Правка города: у админа — только свои, остальное решает сервер флагом can_manage. */
  function canManageCity(city) {
    return canManage() && city.can_manage !== false;
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

  function svgIcon(icon) {
    return (
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      ICONS[icon] +
      "</svg>"
    );
  }

  function makeIconBtn(icon, label, onClick, extraClass) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn-icon" + (extraClass ? " " + extraClass : "");
    b.title = label;
    b.setAttribute("aria-label", label);
    b.innerHTML = svgIcon(icon);
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

  var MODES = [
    { id: "own", hint: "Города, которые ведёте вы" },
    { id: "working", label: "В работе", hint: "Города в работе у всей команды" },
  ];

  function modeLabel(id) {
    if (id === "working") return "В работе";
    return seesAllCities() ? "Все города" : "Мои города";
  }

  function renderModes() {
    var bar = document.getElementById("citiesModes");
    if (!bar) return;
    bar.innerHTML = "";
    MODES.forEach(function (item) {
      var btn = el("button", "tabs__btn", modeLabel(item.id));
      btn.type = "button";
      btn.setAttribute("role", "tab");
      btn.setAttribute("data-mode", item.id);
      var active = mode === item.id;
      if (active) btn.classList.add("is-active");
      btn.setAttribute("aria-selected", active ? "true" : "false");
      btn.title = item.hint;
      btn.addEventListener("click", function () {
        if (mode === item.id) return;
        mode = item.id;
        openDetailId = null;
        renderModes();
        loadAndRender();
      });
      bar.appendChild(btn);
    });
  }

  async function loadAndRender() {
    var listEl = document.getElementById("citiesList");
    if (!listEl) return;
    listEl.innerHTML = '<p class="empty-hint">Загрузка…</p>';
    try {
      var cities = await global.NogaApi.listCities(mode);
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
      listEl.appendChild(
        el(
          "p",
          "empty-hint",
          mode === "working" ? "Городов в работе пока нет" : "Городов пока нет"
        )
      );
      return;
    }
    cities.forEach(function (city) {
      listEl.appendChild(buildCard(city));
    });
  }

  var ORPHAN_QUESTION =
    "К городу не прикреплена нога — заказ отдавать некому. " +
    "Всё равно оставить статус «В работе»?";

  /**
   * Аварии города в работе: заказ некому отдать (нет ноги) или некуда разгрузить
   * (нет разгруза). Про разгрузы молчим у ролей, которым их не показывают.
   */
  function cityProblems(city) {
    if (city.status !== "working") return [];
    var problems = [];
    if (!city.nogas_count) {
      problems.push("Нет ноги");
    }
    if (canSeeRazgruzy() && !(city.razgruzy || []).length) {
      problems.push("Нет разгруза");
    }
    return problems;
  }

  function buildWarning(text) {
    return el("p", "alert-banner", text);
  }

  function appendWarnings(node, problems) {
    problems.forEach(function (text) {
      node.appendChild(buildWarning(text));
    });
  }

  function buildCard(city) {
    var problems = cityProblems(city);
    var orphan = problems.length > 0;
    var card = el("article", "user-card city-card" + (orphan ? " city-card--alert" : ""));

    var top = el("div", "user-card__top");
    var head = el("div");
    head.appendChild(el("p", "user-card__name", city.name));

    var parts = [];
    if (city.min_amount !== null && city.min_amount !== undefined) {
      parts.push(
        "От " + global.NogaDict.formatCompactAmount(city.min_amount, city.min_amount_currency)
      );
    }
    parts.push("Ног: " + city.nogas_count);
    if (canSeeRazgruzy()) parts.push("Разгрузов: " + city.razgruzy.length);
    head.appendChild(el("p", "user-card__meta", parts.join(" · ")));
    if (!canManageCity(city)) {
      head.appendChild(
        el("p", "user-card__meta user-card__meta--history", "Ведёт " + (city.created_by_name || "другой пользователь"))
      );
    }
    top.appendChild(head);
    card.appendChild(top);

    appendWarnings(card, problems);

    if (canSeeRazgruzy() && city.razgruzy.length) {
      var chips = el("div", "chips");
      city.razgruzy.forEach(function (r) {
        chips.appendChild(
          el("span", "chip", r.name + " · " + global.NogaDict.formatPercent(r.commission_percent))
        );
      });
      card.appendChild(chips);
    }

    if (canManageCity(city)) {
      card.appendChild(buildStatusSwitch(city));
    }

    var actions = el("div", "user-card__actions");
    var detailWrap = el("div", "city-card__detail");
    detailWrap.hidden = true;

    var detailBtn = makeIconBtn("detail", "Подробнее", function () {
      toggleDetail(city, detailWrap, detailBtn);
    });
    actions.appendChild(detailBtn);
    if (canManageCity(city)) {
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
        if (item.value === "working" && !city.nogas_count) {
          global.NogaTelegram.confirmAction(ORPHAN_QUESTION, function () {
            patch(city, { status: item.value });
          });
          return;
        }
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

  /** Строка ноги в деталях города: ноги тут все, включая чужие, с карточкой по клику. */
  function buildNogaRow(noga) {
    var flags = [];
    if (noga.is_test) flags.push("тестовая");
    if (!noga.is_active) flags.push("выключена");
    if (!flags.length) flags.push("рабочая");

    var line = el("li", "detail-list__item");
    var head = el("div", "detail-list__head");
    var text = el("div", "detail-list__text");
    text.appendChild(el("span", "detail-list__name", noga.name));
    text.appendChild(
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
    head.appendChild(text);

    var panel = el("div", "detail-list__panel");
    panel.hidden = true;
    var btn = makeIconBtn("detail", "Подробнее", function () {
      if (!panel.hidden) {
        panel.hidden = true;
        panel.innerHTML = "";
        setDetailBtnState(btn, false);
        return;
      }
      panel.hidden = false;
      setDetailBtnState(btn, true);
      global.NogaNogas.renderCard(noga.id, panel);
    });
    head.appendChild(btn);

    line.appendChild(head);
    line.appendChild(panel);
    return line;
  }

  function renderDetail(city, container) {
    container.innerHTML = "";
    appendWarnings(container, cityProblems(city));

    if (global.NogaRoles.can("nogas:read")) {
      container.appendChild(el("p", "detail__title", "Ноги (" + city.nogas.length + ")"));
      if (!city.nogas.length) {
        container.appendChild(el("p", "detail__empty", "Ног в городе пока нет"));
      } else {
        var nogasList = el("ul", "detail-list");
        city.nogas.forEach(function (noga) {
          nogasList.appendChild(buildNogaRow(noga));
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

  function hideSuggest() {
    var list = document.getElementById("citySuggestList");
    if (list) {
      list.hidden = true;
      list.innerHTML = "";
    }
    suggestItems = [];
    suggestActive = -1;
  }

  function setSuggestHint(text) {
    var hint = document.getElementById("citySuggestHint");
    if (!hint) return;
    if (!text) {
      hint.hidden = true;
      hint.textContent = "";
      return;
    }
    hint.hidden = false;
    hint.textContent = text;
  }

  function applyCurrency(code, country) {
    var select = document.getElementById("cityCurrency");
    if (!select || !code) return;
    var has = false;
    Array.prototype.forEach.call(select.options, function (opt) {
      if (opt.value === code) has = true;
    });
    if (!has) return;
    select.value = code;
    var info = global.NogaDict.currency(code);
    var label = info ? info.label : code;
    setSuggestHint(
      country
        ? "Валюта страны: " + label + " (" + country + ")"
        : "Валюта страны: " + label
    );
  }

  function pickSuggest(item) {
    if (!item) return;
    var input = document.getElementById("cityName");
    if (input) input.value = item.name;
    hideSuggest();
    if (item.currency && (!currencyTouched || editingId === null)) {
      currencyTouched = false;
      applyCurrency(item.currency, item.country);
    } else if (item.country) {
      setSuggestHint(item.country);
    }
  }

  function renderSuggest(items) {
    var list = document.getElementById("citySuggestList");
    if (!list) return;
    suggestItems = items || [];
    suggestActive = suggestItems.length ? 0 : -1;
    list.innerHTML = "";
    if (!suggestItems.length) {
      list.hidden = true;
      return;
    }
    suggestItems.forEach(function (item, index) {
      var li = el("li", "city-suggest__item" + (index === 0 ? " is-active" : ""));
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", index === 0 ? "true" : "false");
      li.textContent = item.label || item.name;
      li.addEventListener("mousedown", function (event) {
        event.preventDefault();
        pickSuggest(item);
      });
      list.appendChild(li);
    });
    list.hidden = false;
  }

  function highlightSuggest(index) {
    var list = document.getElementById("citySuggestList");
    if (!list || !suggestItems.length) return;
    suggestActive = (index + suggestItems.length) % suggestItems.length;
    var nodes = list.querySelectorAll(".city-suggest__item");
    Array.prototype.forEach.call(nodes, function (node, i) {
      var on = i === suggestActive;
      node.classList.toggle("is-active", on);
      node.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  async function runSuggest(query) {
    var seq = ++suggestSeq;
    var cleaned = (query || "").trim();
    if (cleaned.length < 2) {
      hideSuggest();
      return;
    }
    try {
      var rows = await global.NogaApi.suggestCities(cleaned, 3);
      if (seq !== suggestSeq) return;
      renderSuggest(rows || []);
      /* При создании сразу подставляем валюту по лучшему совпадению. */
      if (
        editingId === null &&
        !currencyTouched &&
        rows &&
        rows.length &&
        rows[0].currency
      ) {
        applyCurrency(rows[0].currency, rows[0].country);
      }
    } catch (err) {
      if (seq !== suggestSeq) return;
      hideSuggest();
    }
  }

  function scheduleSuggest() {
    if (suggestTimer) clearTimeout(suggestTimer);
    suggestTimer = setTimeout(function () {
      var input = document.getElementById("cityName");
      runSuggest(input ? input.value : "");
    }, 320);
  }

  function bindSuggest() {
    var input = document.getElementById("cityName");
    var currency = document.getElementById("cityCurrency");
    if (!input) return;

    input.addEventListener("input", function () {
      scheduleSuggest();
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") {
        if (!suggestItems.length) return;
        event.preventDefault();
        highlightSuggest(suggestActive + 1);
      } else if (event.key === "ArrowUp") {
        if (!suggestItems.length) return;
        event.preventDefault();
        highlightSuggest(suggestActive - 1);
      } else if (event.key === "Enter" && suggestItems.length && suggestActive >= 0) {
        event.preventDefault();
        pickSuggest(suggestItems[suggestActive]);
      } else if (event.key === "Escape") {
        hideSuggest();
      }
    });
    input.addEventListener("blur", function () {
      setTimeout(hideSuggest, 150);
    });

    if (currency) {
      currency.addEventListener("change", function () {
        currencyTouched = true;
        setSuggestHint("");
      });
    }
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

  /** Свои разгрузы подставляются в новый город: их автор ведёт участок целиком. */
  function ownRazgruzIds() {
    return razgruzy
      .filter(function (r) {
        return r.created_by_me && r.is_active;
      })
      .map(function (r) {
        return r.id;
      });
  }

  function fillRazgruzChecklist(selectedIds, prefilled) {
    var field = document.getElementById("cityRazgruzyField");
    var box = document.getElementById("cityRazgruzy");
    if (!field || !box) return;
    field.hidden = !canSeeRazgruzy();
    box.innerHTML = "";

    if (prefilled && selectedIds.length) {
      box.appendChild(
        el("p", "detail__empty", "Ваши разгрузы отмечены сразу — лишние можно снять")
      );
    }

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
  function fillNogaChecklist(city) {
    var cityId = city ? city.id : null;
    var field = document.getElementById("cityNogasField");
    var box = document.getElementById("cityNogas");
    if (!field || !box) return;
    field.hidden = !canManageNogas();
    box.innerHTML = "";

    // Чужие ноги в городе двигать нельзя — показываем их отдельной подписью,
    // чтобы состав в форме сходился с тем, что видно в деталях города.
    var mineNow = nogas.filter(function (noga) {
      return cityId !== null && noga.city_id === cityId;
    }).length;
    var foreign = city ? Math.max(0, city.nogas_count - mineNow) : 0;
    if (foreign) {
      box.appendChild(
        el(
          "p",
          "detail__empty",
          "Ещё " + foreign + " ног(и) в городе завели другие — их состав менять нельзя"
        )
      );
    }

    if (!nogas.length) {
      box.appendChild(el("p", "detail__empty", "Ваших ног пока нет — добавьте их на экране «Ноги»"));
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

  async function openForm(city) {
    bindForm();
    await loadRazgruzy();
    await loadNogas();
    fillStatusSelect();
    fillCurrencySelect();

    editingId = city ? city.id : null;
    editingCity = city || null;
    currencyTouched = Boolean(city && city.min_amount_currency);
    hideSuggest();
    setSuggestHint("");
    document.getElementById("cityFormTitle").textContent = city
      ? "Изменить город"
      : "Новый город";
    document.getElementById("cityName").value = city ? city.name : "";
    document.getElementById("cityStatus").value = city ? city.status : "working";
    document.getElementById("cityMinAmount").value =
      city && city.min_amount !== null && city.min_amount !== undefined ? city.min_amount : "";
    document.getElementById("cityCurrency").value =
      city && city.min_amount_currency ? city.min_amount_currency : "";

    if (city && city.razgruzy) {
      fillRazgruzChecklist(
        city.razgruzy.map(function (r) {
          return r.id;
        }),
        false
      );
    } else {
      fillRazgruzChecklist(ownRazgruzIds(), true);
    }
    fillNogaChecklist(city || null);

    if (global.NogaProfile && global.NogaProfile.hideBack) global.NogaProfile.hideBack();
    global.NogaViews.show("viewCityCreate");
  }

  function leaveForm() {
    if (suggestTimer) clearTimeout(suggestTimer);
    hideSuggest();
    setSuggestHint("");
    editingId = null;
    editingCity = null;
    show({ mode: mode });
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
    if (formBound) return;
    formBound = true;

    var backBtn = document.getElementById("cityCreateBack");
    if (backBtn) backBtn.addEventListener("click", leaveForm);

    var cancelBtn = document.getElementById("btnCancelCity");
    if (cancelBtn) cancelBtn.addEventListener("click", leaveForm);

    bindSuggest();

    var form = document.getElementById("cityForm");
    if (!form) return;
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var payload = collectPayload();
      if (!payload) return;
      if (payload.status === "working" && nogasAfterSave(payload) === 0) {
        global.NogaTelegram.confirmAction(ORPHAN_QUESTION, function () {
          saveCity(payload);
        });
        return;
      }
      saveCity(payload);
    });
  }

  /** Сколько ног останется в городе после сохранения — с учётом чужих. */
  function nogasAfterSave(payload) {
    if (!editingCity) return payload.noga_ids ? payload.noga_ids.length : 0;
    if (!payload.noga_ids) return editingCity.nogas_count;
    var mineNow = nogas.filter(function (noga) {
      return noga.city_id === editingCity.id;
    }).length;
    var foreign = Math.max(0, editingCity.nogas_count - mineNow);
    return foreign + payload.noga_ids.length;
  }

  async function saveCity(payload) {
    try {
      if (editingId === null) {
        await global.NogaApi.createCity(payload);
      } else {
        await global.NogaApi.updateCity(editingId, payload);
      }
      editingId = null;
      editingCity = null;
      // Состав города мог поменяться — перечитываем ноги, чтобы чек-лист
      // в следующий раз показал актуальную привязку.
      await loadNogas();
      await show({ mode: mode });
      await refreshDashboard();
    } catch (err) {
      global.NogaTelegram.notify(err.message || "Не удалось сохранить город");
    }
  }

  async function show(options) {
    global.NogaViews.show("viewCities");
    if (options && options.mode && options.mode !== mode) {
      mode = options.mode;
      openDetailId = null;
    }
    bindForm();
    renderModes();
    global.NogaNogas.release();
    await loadRazgruzy();
    await loadNogas();
    await loadAndRender();
  }

  /** Вход из меню «+»: отдельный экран создания. */
  async function openCreate() {
    mode = "own";
    await openForm(null);
  }

  function hide() {
    global.NogaNogas.release();
    global.NogaViews.show("viewHome");
  }

  global.NogaCities = {
    show: show,
    hide: hide,
    reload: loadAndRender,
    openCreate: openCreate,
  };
})(window);
