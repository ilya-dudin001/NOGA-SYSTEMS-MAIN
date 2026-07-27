(function (global) {
  "use strict";

  var editingId = null;
  var formBound = false;

  function canManage() {
    return global.NogaRoles.can("razgruz:manage");
  }

  /** Свой разгруз правит автор, чужой — только роли со скоупом на всех. */
  function canManageRazgruz(razgruz) {
    return canManage() && razgruz.can_manage !== false;
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

  async function loadAndRender() {
    var listEl = document.getElementById("razgruzyList");
    if (!listEl) return;
    listEl.innerHTML = '<p class="empty-hint">Загрузка…</p>';
    try {
      renderList(await global.NogaApi.listRazgruzy());
    } catch (err) {
      listEl.innerHTML = "";
      listEl.appendChild(
        el("p", "empty-hint", "Не удалось загрузить: " + (err.message || err.code || "ошибка"))
      );
    }
  }

  function renderList(items) {
    var listEl = document.getElementById("razgruzyList");
    listEl.innerHTML = "";
    if (!items || !items.length) {
      listEl.appendChild(el("p", "empty-hint", "Разгрузов пока нет"));
      return;
    }

    items.forEach(function (r) {
      var card = el("article", "user-card");

      var top = el("div", "user-card__top");
      var head = el("div");
      head.appendChild(
        el("p", "user-card__name", r.name + " — " + global.NogaDict.formatPercent(r.commission_percent))
      );
      head.appendChild(
        el(
          "p",
          "user-card__meta",
          "успешно разгружено: " +
            r.completed_orders +
            " · городов: " +
            r.cities_count +
            " · добавил " +
            (r.created_by_name || "—") +
            " · " +
            global.NogaDict.formatDate(r.created_at)
        )
      );
      if (r.contact) head.appendChild(el("p", "user-card__meta", "контакт: " + r.contact));
      top.appendChild(head);

      var badges = el("div", "user-card__badges");
      badges.appendChild(
        el(
          "span",
          "user-card__badge" + (r.is_active ? "" : " user-card__badge--blocked"),
          r.is_active ? "Активен" : "Выключен"
        )
      );
      top.appendChild(badges);
      card.appendChild(top);

      if (canManageRazgruz(r)) {
        var actions = el("div", "user-card__actions");
        actions.appendChild(
          makeBtn("Изменить", function () {
            openForm(r);
          })
        );
        actions.appendChild(
          makeBtn(
            r.is_active ? "Выключить" : "Включить",
            function () {
              patch(r, { is_active: !r.is_active });
            },
            r.is_active ? "btn-ghost--danger" : ""
          )
        );
        actions.appendChild(
          makeBtn(
            "Удалить",
            function () {
              removeRazgruz(r);
            },
            "btn-ghost--danger"
          )
        );
        card.appendChild(actions);
      }

      listEl.appendChild(card);
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

  async function patch(razgruz, payload) {
    try {
      await global.NogaApi.updateRazgruz(razgruz.id, payload);
      await loadAndRender();
    } catch (err) {
      global.NogaTelegram.notify(err.message || "Не удалось изменить разгруз");
    }
  }

  function citiesQuestion(razgruz, names) {
    var shown = names.slice(0, 5).join(", ");
    if (names.length > 5) shown += " и ещё " + (names.length - 5);
    var head =
      names.length === 1
        ? "Разгруз " + razgruz.name + " привязан к городу: "
        : "Разгруз " + razgruz.name + " привязан к городам: ";
    return (
      head +
      shown +
      ". При удалении разгруза они автоматически от него отвяжутся. Удалить разгруз?"
    );
  }

  function removeRazgruz(razgruz) {
    // У привязанного разгруза имена городов знает только сервер: первый DELETE
    // ничего не удалит, а вернёт 409 со списком — из него и собираем вопрос.
    if (razgruz.cities_count) {
      performDelete(razgruz, false);
      return;
    }
    global.NogaTelegram.confirmAction("Удалить разгруз " + razgruz.name + "?", function () {
      performDelete(razgruz, false);
    });
  }

  async function performDelete(razgruz, detachCities) {
    try {
      await global.NogaApi.deleteRazgruz(razgruz.id, { detachCities: detachCities });
      await loadAndRender();
      await refreshDashboard();
    } catch (err) {
      if (err.code === "RAZGRUZ_HAS_CITIES" && !detachCities) {
        var names = (err.body && err.body.detail && err.body.detail.cities) || [];
        global.NogaTelegram.confirmAction(
          names.length ? citiesQuestion(razgruz, names) : err.message + ". Удалить разгруз?",
          function () {
            performDelete(razgruz, true);
          }
        );
        return;
      }
      global.NogaTelegram.notify(err.message || "Ошибка удаления");
    }
  }

  function openForm(razgruz) {
    var form = document.getElementById("razgruzForm");
    if (!form) return;
    editingId = razgruz ? razgruz.id : null;
    document.getElementById("razgruzFormTitle").textContent = razgruz
      ? "Изменить разгруз"
      : "Новый разгруз";
    document.getElementById("razgruzName").value = razgruz ? razgruz.name : "";
    document.getElementById("razgruzPercent").value = razgruz ? razgruz.commission_percent : "";
    document.getElementById("razgruzContact").value = razgruz && razgruz.contact ? razgruz.contact : "";
    form.hidden = false;
    form.scrollIntoView({ block: "nearest" });
  }

  function closeForm() {
    var form = document.getElementById("razgruzForm");
    if (form) form.hidden = true;
    editingId = null;
  }

  function bindForm() {
    var openBtn = document.getElementById("btnAddRazgruz");
    if (openBtn) openBtn.hidden = !canManage();
    if (formBound) return;
    formBound = true;

    if (openBtn) {
      openBtn.addEventListener("click", function () {
        openForm(null);
      });
    }
    var cancelBtn = document.getElementById("btnCancelRazgruz");
    if (cancelBtn) cancelBtn.addEventListener("click", closeForm);

    var form = document.getElementById("razgruzForm");
    if (!form) return;
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var name = document.getElementById("razgruzName").value.trim();
      if (!name) {
        global.NogaTelegram.notify("Укажите название разгруза");
        return;
      }
      var percent = Number(document.getElementById("razgruzPercent").value || 0);
      if (isNaN(percent) || percent < 0 || percent > 100) {
        global.NogaTelegram.notify("Комиссия должна быть от 0 до 100 %");
        return;
      }
      var payload = {
        name: name,
        commission_percent: percent,
        contact: document.getElementById("razgruzContact").value.trim() || null,
      };
      try {
        if (editingId === null) {
          await global.NogaApi.createRazgruz(payload);
        } else {
          await global.NogaApi.updateRazgruz(editingId, payload);
        }
        closeForm();
        await loadAndRender();
      } catch (err) {
        global.NogaTelegram.notify(err.message || "Не удалось сохранить разгруз");
      }
    });
  }

  function show() {
    global.NogaViews.show("viewRazgruzy");
    bindForm();
    closeForm();
    loadAndRender();
  }

  function hide() {
    global.NogaViews.show("viewHome");
  }

  global.NogaRazgruzy = { show: show, hide: hide, reload: loadAndRender };
})(window);
