/* Справочник банкоматов: поиск по адресу (город / улица / дом). */
(function (global) {
  "use strict";

  var bound = false;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function canAccess() {
    var user = global.NogaRoles.getUser && global.NogaRoles.getUser();
    return !!(
      user &&
      user.features &&
      user.features.places &&
      global.NogaRoles.can("places:read")
    );
  }

  function kindLabel(kind) {
    if (global.NogaDict && global.NogaDict.placeKind) {
      return global.NogaDict.placeKind(kind).label;
    }
    if (kind === "atm") return "Банкомат";
    if (kind === "terminal") return "Терминал";
    return "Объект";
  }

  function formatDistance(meters) {
    var value = Number(meters) || 0;
    if (value < 1000) return Math.round(value) + " м";
    return (value / 1000).toFixed(1).replace(".0", "") + " км";
  }

  function setHint(host, text, isError) {
    host.textContent = "";
    var p = el("p", "empty-hint" + (isError ? " is-error" : ""), text);
    host.appendChild(p);
  }

  function renderItems(host, items, partial) {
    host.textContent = "";
    if (partial) {
      host.appendChild(
        el(
          "p",
          "empty-hint",
          "Показаны сохранённые объекты: ответ карты пришёл не полностью."
        )
      );
    }
    if (!items || !items.length) {
      host.appendChild(el("p", "empty-hint", "Рядом ничего не найдено"));
      return;
    }
    var list = el("div", "bankomaty-list");
    items.forEach(function (item, index) {
      var card = el("article", "user-card bankomaty-card");
      card.style.setProperty("--i", String(index));

      var head = el("div", "user-card__head");
      var title = el("div", "user-card__title");
      title.appendChild(el("span", "user-card__name", item.name || "Без названия"));
      head.appendChild(title);
      card.appendChild(head);

      var meta = el("div", "user-card__meta");
      meta.appendChild(
        el("span", "user-card__badge", kindLabel(item.kind))
      );
      var bank =
        item.bank ||
        (global.NogaDict && global.NogaDict.PLACE_BANK_UNKNOWN) ||
        "Банк не указан";
      if (item.kind === "atm" || item.kind === "terminal") {
        meta.appendChild(el("span", "user-card__line", bank));
      }
      if (item.address) {
        meta.appendChild(el("span", "user-card__line", item.address));
      }
      meta.appendChild(
        el("span", "user-card__line", formatDistance(item.distance_m))
      );
      if (item.from_cache) {
        meta.appendChild(el("span", "user-card__line", "из кэша"));
      }
      card.appendChild(meta);
      list.appendChild(card);
    });
    host.appendChild(list);
  }

  async function onSearch(event) {
    event.preventDefault();
    if (!canAccess()) {
      if (global.NogaTelegram) {
        global.NogaTelegram.notify("Справочник банкоматов недоступен");
      }
      return;
    }
    var city = (document.getElementById("bankomatyCity") || {}).value || "";
    var street = (document.getElementById("bankomatyStreet") || {}).value || "";
    var house = (document.getElementById("bankomatyHouse") || {}).value || "";
    city = String(city).trim();
    street = String(street).trim();
    house = String(house).trim();
    var host = document.getElementById("bankomatyResults");
    if (!city || !street) {
      if (global.NogaTelegram) {
        global.NogaTelegram.notify("Укажите город и улицу");
      }
      return;
    }
    setHint(host, "Ищем…");
    var btn = document.getElementById("bankomatySubmit");
    if (btn) btn.disabled = true;
    try {
      var data = await global.NogaApi.placesNearby({
        city: city,
        street: street,
        house: house || null,
      });
      renderItems(host, data.items || [], !!data.partial);
    } catch (err) {
      var message =
        (err && err.message) || "Не удалось выполнить поиск";
      setHint(host, message, true);
      if (global.NogaTelegram) global.NogaTelegram.notify(message);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function bind() {
    if (bound) return;
    bound = true;
    var form = document.getElementById("bankomatyForm");
    if (form) form.addEventListener("submit", onSearch);
  }

  function show() {
    bind();
    if (!canAccess()) {
      if (global.NogaTelegram) {
        global.NogaTelegram.notify("Справочник банкоматов недоступен");
      }
      return;
    }
    global.NogaViews.show("viewBankomaty");
    var host = document.getElementById("bankomatyResults");
    if (host && !host.childNodes.length) {
      setHint(host, "Введите город и улицу, затем нажмите «Найти»");
    }
  }

  global.NogaBankomaty = { show: show };
})(window);
