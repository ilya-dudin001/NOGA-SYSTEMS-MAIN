(function (global) {
  "use strict";

  var cities = [];
  var formBound = false;
  var editingId = null;
  var openDetailId = null;
  var openContainer = null;
  var openButton = null;
  var openTab = "main";
  // Предпросмотр грузится в blob, ссылки надо отзывать — иначе течёт память.
  var blobUrls = [];

  function canManage() {
    return global.NogaRoles.can("nogas:manage");
  }

  /** Свою ногу правит автор, чужую — только роли со скоупом на всех. */
  function canManageNoga(noga) {
    return canManage() && noga.can_manage !== false;
  }

  function canPersonal() {
    return global.NogaRoles.can("nogas:personal");
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

  function makeBadge(text, extraClass) {
    return el("span", "user-card__badge" + (extraClass ? " " + extraClass : ""), text);
  }

  /* Иконки те же, что на карточках городов: подпись живёт в title/aria-label. */
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
    button.classList.toggle("is-open", open);
    var label = open ? "Свернуть" : "Подробнее";
    button.title = label;
    button.setAttribute("aria-label", label);
  }

  function trackBlob(url) {
    blobUrls.push(url);
    return url;
  }

  function releaseBlobs() {
    blobUrls.forEach(function (url) {
      URL.revokeObjectURL(url);
    });
    blobUrls = [];
  }

  /* ---------- список ---------- */

  /** Свои города плюс общая витрина: ногу можно поставить и в чужой город в работе. */
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

  async function loadAndRender() {
    var listEl = document.getElementById("nogasList");
    if (!listEl) return;
    releaseBlobs();
    listEl.innerHTML = "";
    listEl.appendChild(el("p", "empty-hint", "Загрузка…"));
    try {
      renderList(await global.NogaApi.listNogas());
    } catch (err) {
      listEl.innerHTML = "";
      listEl.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || err.code || "ошибка"))
      );
    }
  }

  function renderList(nogas) {
    var listEl = document.getElementById("nogasList");
    listEl.innerHTML = "";
    if (!nogas || !nogas.length) {
      listEl.appendChild(el("p", "empty-hint", "Ног пока нет"));
      return;
    }
    nogas.forEach(function (noga) {
      listEl.appendChild(buildCard(noga));
    });
  }

  function buildCard(noga) {
    var card = el("article", "user-card");

    var top = el("div", "user-card__top");
    var head = el("div");
    head.appendChild(el("p", "user-card__name", noga.name));
    head.appendChild(el("p", "user-card__meta", noga.city_name || "Без города"));
    if (!noga.city_id) {
      var history = cityHistory(noga);
      if (history.length) {
        var hint = history
          .map(function (item) {
            return item.label.toLowerCase() + ": " + item.value;
          })
          .join(" · ");
        head.appendChild(el("p", "user-card__meta user-card__meta--history", hint));
      }
    }
    top.appendChild(head);

    var badges = el("div", "user-card__badges");
    if (noga.is_test) badges.appendChild(makeBadge("Тест", "user-card__badge--test"));
    if (!noga.is_active) badges.appendChild(makeBadge("Выключена", "user-card__badge--blocked"));
    if (!noga.is_test && noga.is_active) badges.appendChild(makeBadge("Рабочая", ""));
    top.appendChild(badges);
    card.appendChild(top);

    var actions = el("div", "user-card__actions");
    var detailWrap = el("div", "city-card__detail");
    detailWrap.hidden = true;

    var detailBtn = makeIconBtn("detail", "Подробнее", function () {
      toggleDetail(noga, detailWrap, detailBtn);
    });
    actions.appendChild(detailBtn);

    // Тип и статус переключаются в деталях: на карточке остаётся только то,
    // что нужно с одного взгляда.
    if (canManageNoga(noga)) {
      actions.appendChild(
        makeIconBtn("edit", "Изменить", function () {
          openForm(noga);
        })
      );
      actions.appendChild(
        makeIconBtn(
          "remove",
          "Удалить",
          function () {
            removeNoga(noga);
          },
          "btn-icon--danger"
        )
      );
    }

    card.appendChild(actions);
    card.appendChild(detailWrap);

    // Список перерисовывается целиком после каждой правки — возвращаем
    // раскрытые детали на место, чтобы они не схлопывались под пользователем.
    if (openDetailId === noga.id) {
      toggleDetail(noga, detailWrap, detailBtn);
    }
    return card;
  }

  /* ---------- детали ---------- */

  function closeOpenDetail() {
    if (openContainer) {
      openContainer.hidden = true;
      openContainer.innerHTML = "";
    }
    setDetailBtnState(openButton, false);
    openContainer = null;
    openButton = null;
    openDetailId = null;
  }

  async function toggleDetail(noga, container, button) {
    if (!container.hidden) {
      closeOpenDetail();
      return;
    }
    // Раскрытым держим только один блок: иначе reloadDetail не поймёт, какой обновлять.
    if (openContainer && openContainer !== container) closeOpenDetail();

    openDetailId = noga.id;
    openContainer = container;
    openButton = button || null;
    container.hidden = false;
    container.innerHTML = "";
    container.appendChild(el("p", "empty-hint", "Загрузка…"));
    setDetailBtnState(button, true);

    try {
      var detail = await global.NogaApi.getNoga(noga.id);
      renderDetail(detail, container);
    } catch (err) {
      container.innerHTML = "";
      container.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || "ошибка"))
      );
    }
  }

  function renderDetail(noga, container) {
    // Панель собирается заново, прошлые blob-ссылки больше никому не нужны.
    releaseBlobs();
    container.innerHTML = "";

    var tabs = [{ id: "main", label: "Основное" }];
    if (noga.has_personal_access) tabs.push({ id: "personal", label: "Личные данные" });
    if (!noga.has_personal_access) openTab = "main";

    var bar = el("div", "tabs");
    bar.setAttribute("role", "tablist");
    var panel = el("div", "tabs__panel");

    tabs.forEach(function (tab) {
      var btn = el("button", "tabs__btn", tab.label);
      btn.type = "button";
      btn.setAttribute("role", "tab");
      var active = openTab === tab.id;
      if (active) btn.classList.add("is-active");
      btn.setAttribute("aria-selected", active ? "true" : "false");
      btn.addEventListener("click", function () {
        openTab = tab.id;
        renderDetail(noga, container);
      });
      bar.appendChild(btn);
    });

    container.appendChild(bar);
    container.appendChild(panel);

    if (openTab === "personal" && noga.has_personal_access) {
      renderPersonalTab(noga, panel);
    } else {
      renderMainTab(noga, panel);
    }
  }

  /** История привязки: показываем только то, что не совпадает с текущим городом. */
  function cityHistory(noga) {
    var initial = noga.initial_city_name || null;
    var last = noga.last_city_name || null;
    if (noga.city_name) {
      if (initial === noga.city_name) initial = null;
      if (last === noga.city_name) last = null;
    }
    if (initial && last && initial !== last) {
      return [
        { label: "Город при добавлении", value: initial },
        { label: "Последний город", value: last },
      ];
    }
    var single = initial || last;
    return single ? [{ label: "Была прикреплена к городу", value: single }] : [];
  }

  function renderMainTab(noga, host, forceReadonly) {
    var list = el("ul", "detail-list");

    function row(name, value, history) {
      var line = el("li", "detail-list__item" + (history ? " detail-list__item--history" : ""));
      line.appendChild(el("span", "detail-list__name", name));
      line.appendChild(el("span", "detail-list__meta", value));
      list.appendChild(line);
    }

    row("Город", noga.city_name || "не прикреплена");
    cityHistory(noga).forEach(function (item) {
      row(item.label, item.value, true);
    });
    row("Тип", noga.is_test ? "тестовая" : "рабочая");
    row("Статус", noga.is_active ? "включена" : "выключена");
    row("Добавил", noga.created_by_name || "—");
    row("Дата добавления", global.NogaDict.formatDate(noga.created_at));
    host.appendChild(list);

    if (!forceReadonly && canManageNoga(noga)) {
      var actions = el("div", "user-card__actions");
      actions.appendChild(
        makeBtn(noga.is_test ? "Сделать рабочей" : "Сделать тестовой", function () {
          patch(noga, { is_test: !noga.is_test });
        })
      );
      actions.appendChild(
        makeBtn(
          noga.is_active ? "Выключить" : "Включить",
          function () {
            patch(noga, { is_active: !noga.is_active });
          },
          noga.is_active ? "btn-ghost--danger" : ""
        )
      );
      host.appendChild(actions);
    }

    if (!noga.has_personal_access) {
      host.appendChild(el("p", "detail__empty", "Нет доступа к личным данным ноги"));
    }
  }

  /** Карточка ноги внутри чужого экрана (детали города): только чтение. */
  async function renderCard(nogaId, container) {
    container.innerHTML = "";
    container.appendChild(el("p", "empty-hint", "Загрузка…"));
    try {
      var noga = await global.NogaApi.getNoga(nogaId);
      container.innerHTML = "";
      renderMainTab(noga, container, true);
      if (noga.has_personal_access) {
        container.appendChild(el("p", "detail__title", "Личные данные"));
        renderPersonalTab(noga, container, true);
      }
      if (!canManageNoga(noga)) {
        container.appendChild(
          el("p", "detail__empty", "Ногу завёл " + (noga.created_by_name || "другой пользователь"))
        );
      }
    } catch (err) {
      container.innerHTML = "";
      container.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || "ошибка"))
      );
    }
  }

  /* ---------- личные данные ---------- */

  function renderPersonalTab(noga, host, forceReadonly) {
    var editable = !forceReadonly && canManageNoga(noga);

    var addressField = el("div", "field");
    var addressLabel = el("label", null, "Домашний адрес");
    // id уникален по ноге: в деталях города можно раскрыть несколько карточек сразу.
    var addressId = "nogaAddress-" + noga.id;
    addressLabel.setAttribute("for", addressId);
    addressField.appendChild(addressLabel);
    var address = document.createElement("textarea");
    address.id = addressId;
    address.rows = 2;
    address.placeholder = "Город, улица, дом, квартира";
    address.value = noga.address || "";
    address.disabled = !editable;
    addressField.appendChild(address);
    host.appendChild(addressField);

    var phones = buildRepeatable("Номера телефонов", noga.phones, "+7 900 000-00-00", editable);
    host.appendChild(phones.field);
    var telegrams = buildRepeatable("Контакты Telegram", noga.telegrams, "@username", editable);
    host.appendChild(telegrams.field);

    if (editable) {
      var save = el("button", "btn-gold", "Сохранить личные данные");
      save.type = "button";
      save.addEventListener("click", async function () {
        save.disabled = true;
        try {
          await global.NogaApi.updateNoga(noga.id, {
            address: address.value.trim() ? address.value.trim() : null,
            phones: phones.values(),
            telegrams: telegrams.values(),
          });
          global.NogaTelegram.notify("Личные данные сохранены");
          await reloadDetail(noga.id);
        } catch (err) {
          global.NogaTelegram.notify(err.message || "Не удалось сохранить");
        } finally {
          save.disabled = false;
        }
      });
      host.appendChild(save);
    }

    global.NogaDict.NOGA_FILE_KINDS.forEach(function (kind) {
      host.appendChild(buildFileBlock(noga, kind, editable));
    });
  }

  /** Поле со списком значений: строки можно добавлять и удалять. */
  function buildRepeatable(label, values, placeholder, editable) {
    var field = el("div", "field");
    field.appendChild(el("label", null, label));
    var box = el("div", "repeat");
    field.appendChild(box);

    function addRow(value) {
      var row = el("div", "repeat__row");
      var input = document.createElement("input");
      input.type = "text";
      input.placeholder = placeholder;
      input.value = value || "";
      input.disabled = !editable;
      row.appendChild(input);
      if (editable) {
        row.appendChild(
          makeBtn(
            "×",
            function () {
              row.remove();
              if (!box.querySelector("input")) addRow("");
            },
            "btn-ghost--icon"
          )
        );
      }
      box.appendChild(row);
      return input;
    }

    var initial = (values || []).filter(function (v) {
      return v;
    });
    if (!initial.length) {
      addRow("");
    } else {
      initial.forEach(addRow);
    }

    if (editable) {
      var add = makeBtn("+ Добавить", function () {
        addRow("").focus();
      });
      field.appendChild(add);
    }

    return {
      field: field,
      values: function () {
        var out = [];
        Array.prototype.forEach.call(box.querySelectorAll("input"), function (input) {
          var value = input.value.trim();
          if (value) out.push(value);
        });
        return out;
      },
    };
  }

  function buildFileBlock(noga, kind, editable) {
    var block = el("section", "file-block");
    block.appendChild(el("p", "file-block__title", kind.label));
    block.appendChild(el("p", "file-block__hint", kind.hint));

    var items = el("div", "file-block__items");
    block.appendChild(items);

    var own = (noga.files || []).filter(function (file) {
      return file.kind === kind.value;
    });
    if (!own.length) {
      items.appendChild(el("p", "detail__empty", "Файлов нет"));
    } else {
      own.forEach(function (file) {
        items.appendChild(buildFileItem(noga, file, kind, editable));
      });
    }

    if (editable) {
      var picker = el("label", "file-upload");
      var input = document.createElement("input");
      input.type = "file";
      input.accept = kind.accept;
      input.hidden = true;
      picker.appendChild(input);
      picker.appendChild(el("span", "file-upload__btn", "Загрузить"));
      var status = el("span", "file-upload__status");
      picker.appendChild(status);

      input.addEventListener("change", async function () {
        var file = input.files && input.files[0];
        if (!file) return;
        status.textContent = "Загрузка…";
        try {
          await global.NogaApi.uploadNogaFile(noga.id, kind.value, file);
          await reloadDetail(noga.id);
        } catch (err) {
          status.textContent = "";
          global.NogaTelegram.notify(err.message || "Не удалось загрузить файл");
        } finally {
          input.value = "";
        }
      });
      block.appendChild(picker);
    }

    return block;
  }

  function buildFileItem(noga, file, kind, editable) {
    var item = el("figure", "file-item");
    var holder = el("div", "file-item__media");
    holder.appendChild(el("span", "file-item__loading", "Загрузка…"));
    item.appendChild(holder);

    var caption = el("figcaption", "file-item__caption");
    caption.appendChild(el("span", "file-item__name", file.original_name));
    caption.appendChild(
      el(
        "span",
        "detail-list__meta",
        global.NogaDict.formatSize(file.size_bytes) +
          " · " +
          global.NogaDict.formatDate(file.created_at) +
          " · " +
          (file.uploaded_by_name || "—")
      )
    );
    item.appendChild(caption);

    var actions = el("div", "file-item__actions");
    item.appendChild(actions);

    loadPreview(noga.id, file, kind, holder, actions);

    if (editable) {
      actions.appendChild(
        makeBtn(
          "Удалить",
          function () {
            removeFile(noga, file);
          },
          "btn-ghost--danger"
        )
      );
    }
    return item;
  }

  async function loadPreview(nogaId, file, kind, holder, actions) {
    try {
      var blob = await global.NogaApi.nogaFileBlob(nogaId, file.id);
      var url = trackBlob(URL.createObjectURL(blob));
      holder.innerHTML = "";

      if (kind.video) {
        var video = document.createElement("video");
        video.src = url;
        video.controls = true;
        video.preload = "metadata";
        video.className = "file-item__video";
        holder.appendChild(video);
      } else {
        var img = document.createElement("img");
        img.className = "file-item__img";
        img.alt = file.original_name;
        // HEIC/HEIF Chrome и Android не рисуют — показываем подсказку вместо битой картинки.
        img.addEventListener("error", function () {
          holder.innerHTML = "";
          holder.appendChild(
            el("span", "file-item__loading", "Браузер не показывает этот формат — скачайте файл")
          );
        });
        img.src = url;
        holder.appendChild(img);
      }

      var download = el("a", "btn-ghost", "Скачать");
      download.href = url;
      download.download = file.original_name;
      actions.insertBefore(download, actions.firstChild);
    } catch (err) {
      holder.innerHTML = "";
      holder.appendChild(
        el("span", "file-item__loading", "Не открылся: " + (err.message || "ошибка"))
      );
    }
  }

  function removeFile(noga, file) {
    global.NogaTelegram.confirmAction("Удалить файл " + file.original_name + "?", async function () {
      try {
        await global.NogaApi.deleteNogaFile(noga.id, file.id);
        await reloadDetail(noga.id);
      } catch (err) {
        global.NogaTelegram.notify(err.message || "Ошибка удаления");
      }
    });
  }

  /** Перерисовывает только раскрытый блок деталей, список не трогаем. */
  async function reloadDetail(nogaId) {
    if (openDetailId !== nogaId || !openContainer) return;
    var container = openContainer;
    try {
      var detail = await global.NogaApi.getNoga(nogaId);
      renderDetail(detail, container);
    } catch (err) {
      global.NogaTelegram.notify(err.message || "Не удалось обновить");
    }
  }

  /* ---------- запись ---------- */

  async function patch(noga, payload) {
    try {
      await global.NogaApi.updateNoga(noga.id, payload);
      await loadAndRender();
    } catch (err) {
      global.NogaTelegram.notify(err.message || "Не удалось изменить");
    }
  }

  function removeNoga(noga) {
    var where = noga.city_name ? " (" + noga.city_name + ")" : "";
    global.NogaTelegram.confirmAction("Удалить ногу " + noga.name + where + "?", async function () {
      try {
        await global.NogaApi.deleteNoga(noga.id);
        if (openDetailId === noga.id) closeOpenDetail();
        await loadAndRender();
      } catch (err) {
        global.NogaTelegram.notify(err.message || "Ошибка удаления");
      }
    });
  }

  /* ---------- форма ---------- */

  function fillCitySelect(selectedId) {
    var select = document.getElementById("nogaCity");
    if (!select) return;
    select.innerHTML = "";

    var none = document.createElement("option");
    none.value = "";
    none.textContent = "Без города";
    select.appendChild(none);

    cities.forEach(function (city) {
      var opt = document.createElement("option");
      opt.value = String(city.id);
      var status = global.NogaDict.cityStatus(city.status);
      opt.textContent =
        city.status === "working" ? city.name : city.name + " (" + status.short + ")";
      select.appendChild(opt);
    });

    var newOpt = document.createElement("option");
    newOpt.value = "__new__";
    newOpt.textContent = "+ Новый город";
    select.appendChild(newOpt);

    select.value = selectedId === null || selectedId === undefined ? "" : String(selectedId);
    toggleNewCityField();
  }

  function toggleNewCityField() {
    var select = document.getElementById("nogaCity");
    var wrap = document.getElementById("nogaCityWrap");
    var input = document.getElementById("nogaCityName");
    if (!select || !wrap || !input) return;
    var isNew = select.value === "__new__";
    wrap.hidden = !isNew;
    input.required = isNew;
    if (!isNew) input.value = "";
  }

  function setTestSwitch(isTest) {
    var buttons = document.querySelectorAll("#nogaTestSwitch .segmented__btn");
    var hidden = document.getElementById("nogaIsTest");
    Array.prototype.forEach.call(buttons, function (btn) {
      var active = btn.getAttribute("data-value") === (isTest ? "true" : "false");
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (hidden) hidden.value = isTest ? "true" : "false";
  }

  function openForm(noga) {
    var form = document.getElementById("nogaForm");
    if (!form) return;

    editingId = noga ? noga.id : null;
    document.getElementById("nogaFormTitle").textContent = noga ? "Изменить ногу" : "Новая нога";
    document.getElementById("nogaName").value = noga ? noga.name : "";
    fillCitySelect(noga ? noga.city_id : null);
    setTestSwitch(noga ? noga.is_test : false);

    form.hidden = false;
    form.scrollIntoView({ block: "nearest" });
  }

  function closeForm() {
    var form = document.getElementById("nogaForm");
    if (form) form.hidden = true;
    editingId = null;
  }

  function collectPayload() {
    var name = document.getElementById("nogaName").value.trim();
    if (!name) {
      global.NogaTelegram.notify("Укажите имя ноги");
      return null;
    }

    var cityValue = document.getElementById("nogaCity").value;
    var payload = { name: name, is_test: document.getElementById("nogaIsTest").value === "true" };

    if (cityValue === "__new__") {
      var cityName = document.getElementById("nogaCityName").value.trim();
      if (!cityName) {
        global.NogaTelegram.notify("Укажите название нового города");
        return null;
      }
      payload.city_name = cityName;
    } else {
      payload.city_id = cityValue ? Number(cityValue) : null;
    }
    return payload;
  }

  function bindForm() {
    if (formBound) return;
    formBound = true;

    var cancelBtn = document.getElementById("btnCancelNoga");
    if (cancelBtn) cancelBtn.addEventListener("click", closeForm);

    var citySelect = document.getElementById("nogaCity");
    if (citySelect) citySelect.addEventListener("change", toggleNewCityField);

    var buttons = document.querySelectorAll("#nogaTestSwitch .segmented__btn");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        setTestSwitch(btn.getAttribute("data-value") === "true");
      });
    });

    var form = document.getElementById("nogaForm");
    if (!form) return;
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var payload = collectPayload();
      if (!payload) return;
      try {
        if (editingId === null) {
          await global.NogaApi.createNoga(payload);
        } else {
          await global.NogaApi.updateNoga(editingId, payload);
        }
        closeForm();
        await loadCities();
        await loadAndRender();
      } catch (err) {
        global.NogaTelegram.notify(err.message || "Не удалось сохранить ногу");
      }
    });
  }

  async function show() {
    global.NogaViews.show("viewNogas");
    bindForm();
    closeForm();
    await loadCities();
    await loadAndRender();
  }

  /** Вход из меню «+»: экран уже с открытой формой новой ноги. */
  async function openCreate() {
    await show();
    openForm(null);
  }

  function hide() {
    releaseBlobs();
    global.NogaViews.show("viewHome");
  }

  global.NogaNogas = {
    show: show,
    hide: hide,
    reload: loadAndRender,
    openCreate: openCreate,
    renderCard: renderCard,
    release: releaseBlobs,
  };
})(window);
