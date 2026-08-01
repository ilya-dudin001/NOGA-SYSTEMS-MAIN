/* Статистика: оборот, справочники и полный архив трубок (owner / правая рука). */
(function (global) {
  "use strict";

  var PAGE_SIZES = [10, 25, 50, 100];
  var PREVIEW_LIMIT = 5;
  var archivePage = 0;
  var archivePageSize = 25;
  var archiveBound = false;

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

  function format(value) {
    return global.NogaDict.formatNumber(value || 0);
  }

  function canAccess() {
    return global.NogaRoles.can("stats:read");
  }

  function operationNumber(id) {
    var value = String(id);
    while (value.length < 6) value = "0" + value;
    return "EM-" + value;
  }

  function statusPill(value) {
    var info = global.NogaDict.trubkaStatus(value);
    var pill = el("span", "em-pill " + info.cls, info.label);
    pill.insertBefore(icon(value === "vyplacheno" ? "check-circle" : "clock"), pill.firstChild);
    return pill;
  }

  /** Компактная строка архива: номер, статус, город · сумма + кнопка деталей. */
  function trubkaRow(trubka, back) {
    var row = el("div", "em-oprow stats-trubka-row");
    row.appendChild(el("span", "em-oprow__id em-ellipsis", operationNumber(trubka.id)));

    var side = el("span", "em-oprow__side");
    side.appendChild(statusPill(trubka.status));
    row.appendChild(side);

    var meta = el("span", "em-oprow__meta");
    meta.appendChild(document.createTextNode(trubka.city_name || "—"));
    meta.appendChild(el("span", "em-oprow__sep", " · "));
    meta.appendChild(
      document.createTextNode(
        global.NogaDict.formatCompactAmount(trubka.amount, trubka.amount_currency) || "—"
      )
    );
    row.appendChild(meta);

    var openBtn = el("button", "em-btn-icon stats-trubka-row__open");
    openBtn.type = "button";
    openBtn.setAttribute("aria-label", "Открыть трубку " + operationNumber(trubka.id));
    openBtn.title = "Открыть";
    openBtn.appendChild(icon("chevron-right"));
    openBtn.addEventListener("click", function () {
      if (global.NogaTrubki) {
        global.NogaTrubki.openDetail(trubka.id, { back: back });
      }
    });
    row.appendChild(openBtn);
    return row;
  }

  function renderTrubkaList(host, items, back, emptyText) {
    host.innerHTML = "";
    if (!items || !items.length) {
      host.appendChild(el("p", "empty-hint", emptyText || "Трубок пока нет"));
      return;
    }
    var list = el("div", "em-oplist");
    items.forEach(function (trubka) {
      list.appendChild(trubkaRow(trubka, back));
    });
    host.appendChild(list);
    hydrate(host);
  }

  /** Плитка «число + подпись» в оформлении дашборда, но без реакции на клик. */
  function statCard(value, label, options) {
    var card = el("article", "stat stat--static");
    var top = el("div", "stat__top");
    var num = el("span", "stat__num" + (options && options.gold ? " stat__num--gold" : ""), value);
    top.appendChild(num);
    if (options && options.dot) top.appendChild(el("span", "status-dot " + options.dot));
    card.appendChild(top);
    card.appendChild(el("span", "stat__label", label));
    return card;
  }

  function block(title, cards, columns) {
    var wrap = el("section", "stats-block");
    wrap.appendChild(el("p", "detail__title", title));
    var grid = el("div", "stats" + (columns === 2 ? " stats--duo" : ""));
    cards.forEach(function (card) {
      grid.appendChild(card);
    });
    wrap.appendChild(grid);
    return wrap;
  }

  function renderSummary(summary) {
    var body = document.getElementById("statsBody");
    if (!body) return;
    body.innerHTML = "";
    summary = summary || {};
    var cities = summary.cities || {};

    if (global.NogaRoles.can("dashboard:global")) {
      body.appendChild(
        block(
          "Оборот за сегодня",
          [
            statCard(format(summary.turnover_rub) + " ₽", "Рубли", { gold: true }),
            statCard(format(summary.turnover_usd) + " $", "USD эквивалент", { gold: true }),
          ],
          2
        )
      );
    }

    var tubes = el("section", "stats-block");
    tubes.appendChild(el("p", "detail__title", "Трубки"));
    var previewHost = el("div", "stats-trubki-preview");
    previewHost.appendChild(el("p", "empty-hint", "Загрузка…"));
    tubes.appendChild(previewHost);
    body.appendChild(tubes);
    loadPreview(previewHost);

    if (global.NogaRoles.can("cities:read")) {
      body.appendChild(
        block(
          "Города",
          [
            statCard(format(cities.total), "Всего", { gold: true }),
            statCard(format(cities.working), "В работе", { dot: "status-dot--working" }),
            statCard(format(cities.paused), "Стоп врем.", { dot: "status-dot--paused" }),
            statCard(format(cities.stopped), "Стоп полн.", { dot: "status-dot--stopped" }),
          ],
          2
        )
      );

      var directories = [statCard(format(cities.nogas), "Ног в системе")];
      if (global.NogaRoles.can("razgruz:read")) {
        directories.push(statCard(format(cities.razgruzy), "Разгрузов"));
      }
      body.appendChild(block("Справочники", directories, 2));
    }
  }

  async function loadPreview(host) {
    try {
      var page = await global.NogaApi.listTrubkiPage({
        limit: PREVIEW_LIMIT,
        offset: 0,
      });
      host.innerHTML = "";
      renderTrubkaList(host, page.items || [], "stats", "Трубок пока нет");
      if ((page.items || []).length) {
        var more = el(
          "button",
          "em-btn em-btn--ghost em-btn--block em-btn--sm stats-trubki-more",
          "Показать все"
        );
        more.type = "button";
        more.addEventListener("click", showAllTrubki);
        host.appendChild(more);
      }
    } catch (err) {
      host.innerHTML = "";
      host.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || err.code || "ошибка"))
      );
    }
  }

  async function loadAndRender() {
    var body = document.getElementById("statsBody");
    if (!body) return;
    body.innerHTML = "";
    body.appendChild(el("p", "empty-hint", "Загрузка…"));
    try {
      renderSummary(await global.NogaApi.dashboardSummary());
    } catch (err) {
      body.innerHTML = "";
      body.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || err.code || "ошибка"))
      );
    }
  }

  function bindArchive() {
    if (archiveBound) return;
    archiveBound = true;

    var back = document.getElementById("statsTrubkiBack");
    if (back) {
      back.addEventListener("click", function () {
        show();
      });
    }

    var sizeSelect = document.getElementById("statsTrubkiPageSize");
    if (sizeSelect) {
      sizeSelect.innerHTML = "";
      PAGE_SIZES.forEach(function (size) {
        var option = el("option", null, String(size));
        option.value = String(size);
        sizeSelect.appendChild(option);
      });
      sizeSelect.value = String(archivePageSize);
      sizeSelect.addEventListener("change", function () {
        archivePageSize = Number(sizeSelect.value) || 25;
        archivePage = 0;
        loadArchivePage();
      });
    }

    var prev = document.getElementById("statsTrubkiPrev");
    var next = document.getElementById("statsTrubkiNext");
    if (prev) {
      prev.addEventListener("click", function () {
        if (archivePage <= 0) return;
        archivePage -= 1;
        loadArchivePage();
      });
    }
    if (next) {
      next.addEventListener("click", function () {
        archivePage += 1;
        loadArchivePage();
      });
    }
  }

  async function loadArchivePage() {
    var host = document.getElementById("statsTrubkiList");
    var meta = document.getElementById("statsTrubkiMeta");
    var prev = document.getElementById("statsTrubkiPrev");
    var next = document.getElementById("statsTrubkiNext");
    if (!host) return;

    host.innerHTML = "";
    host.appendChild(el("p", "empty-hint", "Загрузка…"));
    try {
      var page = await global.NogaApi.listTrubkiPage({
        limit: archivePageSize,
        offset: archivePage * archivePageSize,
      });
      var total = page.total || 0;
      var pages = Math.max(1, Math.ceil(total / archivePageSize));
      if (archivePage >= pages) {
        archivePage = Math.max(0, pages - 1);
        if (total > 0) {
          return loadArchivePage();
        }
      }
      renderTrubkaList(host, page.items || [], "statsTrubki", "Трубок пока нет");

      var from = total === 0 ? 0 : archivePage * archivePageSize + 1;
      var to = Math.min(total, (archivePage + 1) * archivePageSize);
      if (meta) {
        meta.textContent =
          total === 0
            ? "Нет записей"
            : from + "–" + to + " из " + format(total) + " · стр. " + (archivePage + 1) + "/" + pages;
      }
      if (prev) prev.disabled = archivePage <= 0;
      if (next) next.disabled = archivePage + 1 >= pages || total === 0;
    } catch (err) {
      host.innerHTML = "";
      host.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || err.code || "ошибка"))
      );
      if (meta) meta.textContent = "";
      if (prev) prev.disabled = true;
      if (next) next.disabled = true;
    }
  }

  function show() {
    if (!canAccess()) {
      global.NogaViews.show("viewProfile");
      return;
    }
    global.NogaViews.show("viewStats");
    loadAndRender();
  }

  function showAllTrubki() {
    if (!canAccess()) {
      global.NogaViews.show("viewProfile");
      return;
    }
    bindArchive();
    var sizeSelect = document.getElementById("statsTrubkiPageSize");
    if (sizeSelect) sizeSelect.value = String(archivePageSize);
    global.NogaViews.show("viewStatsTrubki");
    loadArchivePage();
  }

  function hide() {
    global.NogaViews.show("viewHome");
  }

  global.NogaStats = {
    show: show,
    hide: hide,
    reload: loadAndRender,
    showAllTrubki: showAllTrubki,
  };
})(window);
