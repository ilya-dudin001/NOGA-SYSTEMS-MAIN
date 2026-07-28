/* Статистика: общесистемные цифры из сводки дашборда, без разреза «мои». */
(function (global) {
  "use strict";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function format(value) {
    return global.NogaDict.formatNumber(value || 0);
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

  function render(summary) {
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

    var operations = block("Операции за сегодня", [
      statCard(format(summary.created), "Создано"),
      statCard(format(summary.in_progress), "В работе"),
      statCard(format(summary.entries), "Заходов"),
      statCard(format(summary.paid), "Выплачено"),
      statCard(format(summary.remaining), "Осталось"),
      statCard(format(summary.total_operations), "Всего операций"),
    ]);
    operations.appendChild(
      el("p", "stats-block__hint", "Раздел операций ещё не запущен — цифры появятся вместе с ним")
    );
    body.appendChild(operations);

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

  async function loadAndRender() {
    var body = document.getElementById("statsBody");
    if (!body) return;
    body.innerHTML = "";
    body.appendChild(el("p", "empty-hint", "Загрузка…"));
    try {
      render(await global.NogaApi.dashboardSummary());
    } catch (err) {
      body.innerHTML = "";
      body.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || err.code || "ошибка"))
      );
    }
  }

  function show() {
    global.NogaViews.show("viewStats");
    loadAndRender();
  }

  function hide() {
    global.NogaViews.show("viewHome");
  }

  global.NogaStats = { show: show, hide: hide, reload: loadAndRender };
})(window);
