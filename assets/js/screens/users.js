(function (global) {
  "use strict";

  var ROLE_OPTIONS = [
    { value: "owner", label: "Owner" },
    { value: "right_hand", label: "Правая рука" },
    { value: "admin", label: "Администратор" },
    { value: "noga", label: "Нога" },
  ];

  function roleLabel(role) {
    for (var i = 0; i < ROLE_OPTIONS.length; i++) {
      if (ROLE_OPTIONS[i].value === role) return ROLE_OPTIONS[i].label;
    }
    return role;
  }

  function canManage() {
    return global.NogaRoles.can("users:manage");
  }

  function canDelete() {
    return global.NogaRoles.can("users:delete");
  }

  async function loadAndRender() {
    var listEl = document.getElementById("usersList");
    if (!listEl) return;
    listEl.innerHTML = '<p class="empty-hint">Загрузка…</p>';
    try {
      var users = await global.NogaApi.listUsers();
      renderList(users);
    } catch (err) {
      listEl.innerHTML =
        '<p class="empty-hint">Не удалось загрузить: ' +
        (err.message || err.code || "ошибка") +
        "</p>";
    }
  }

  function renderList(users) {
    var listEl = document.getElementById("usersList");
    if (!users || !users.length) {
      listEl.innerHTML = '<p class="empty-hint">Пользователей пока нет</p>';
      return;
    }
    listEl.innerHTML = "";
    users.forEach(function (u) {
      var card = document.createElement("article");
      card.className = "user-card";
      var blocked = u.status === "blocked";
      var badgeClass = blocked ? "user-card__badge user-card__badge--blocked" : "user-card__badge";
      var badgeText = blocked ? "Заблокирован" : roleLabel(u.role);
      var uname = u.username ? "@" + u.username : "—";

      card.innerHTML =
        '<div class="user-card__top">' +
        "<div>" +
        '<p class="user-card__name"></p>' +
        '<p class="user-card__meta"></p>' +
        "</div>" +
        '<span class="' +
        badgeClass +
        '"></span>' +
        "</div>" +
        '<div class="user-card__actions"></div>';

      card.querySelector(".user-card__name").textContent = u.display_name;
      card.querySelector(".user-card__meta").textContent =
        "ID " + u.telegram_id + " · " + uname;
      card.querySelector(".user-card__badge").textContent = badgeText;

      var actions = card.querySelector(".user-card__actions");
      if (canManage()) {
        actions.appendChild(
          makeBtn("Роль", function () {
            changeRole(u);
          })
        );
        actions.appendChild(
          makeBtn(blocked ? "Разблок." : "Блок", function () {
            toggleBlock(u);
          }, blocked ? "" : "btn-ghost--danger")
        );
      }
      if (canDelete()) {
        actions.appendChild(
          makeBtn("Удалить", function () {
            removeUser(u);
          }, "btn-ghost--danger")
        );
      }
      listEl.appendChild(card);
    });
  }

  function makeBtn(label, onClick, extraClass) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn-ghost" + (extraClass ? " " + extraClass : "");
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
  }

  async function changeRole(u) {
    var options = ROLE_OPTIONS.map(function (r) {
      return r.value;
    }).join(", ");
    var next = window.prompt("Новая роль (" + options + "):", u.role);
    if (!next || next === u.role) return;
    try {
      await global.NogaApi.updateUser(u.id, { role: next });
      await loadAndRender();
    } catch (err) {
      global.NogaTelegram.notify(err.message || "Ошибка смены роли");
    }
  }

  async function toggleBlock(u) {
    var next = u.status === "blocked" ? "active" : "blocked";
    try {
      await global.NogaApi.updateUser(u.id, { status: next });
      await loadAndRender();
    } catch (err) {
      global.NogaTelegram.notify(err.message || "Ошибка");
    }
  }

  function removeUser(u) {
    var question =
      "Удалить пользователя " +
      u.display_name +
      " (ID " +
      u.telegram_id +
      ")?\nДоступ пропадёт сразу, восстановить нельзя.";

    global.NogaTelegram.confirmAction(question, async function () {
      try {
        await global.NogaApi.deleteUser(u.id);
        await loadAndRender();
      } catch (err) {
        global.NogaTelegram.notify(err.message || "Ошибка удаления");
      }
    });
  }

  var formBound = false;

  function bindForm() {
    var form = document.getElementById("userCreateForm");
    var openBtn = document.getElementById("btnAddUser");
    var cancelBtn = document.getElementById("btnCancelUser");
    if (openBtn) openBtn.hidden = !canManage();
    if (formBound) return;
    formBound = true;
    if (openBtn) {
      openBtn.addEventListener("click", function () {
        if (form) form.hidden = false;
      });
    }
    if (cancelBtn && form) {
      cancelBtn.addEventListener("click", function () {
        form.hidden = true;
      });
    }
    if (form) {
      form.addEventListener("submit", async function (e) {
        e.preventDefault();
        var tid = document.getElementById("newUserTelegramId").value;
        var role = document.getElementById("newUserRole").value;
        var name = document.getElementById("newUserName").value;
        try {
          await global.NogaApi.createUser({
            telegram_id: Number(tid),
            role: role,
            display_name: name || undefined,
          });
          form.reset();
          form.hidden = true;
          await loadAndRender();
        } catch (err) {
          global.NogaTelegram.notify(err.message || "Не удалось добавить");
        }
      });
    }
  }

  function show() {
    global.NogaViews.show("viewUsers");
    bindForm();
    loadAndRender();
  }

  function hide() {
    global.NogaViews.show("viewHome");
  }

  global.NogaUsers = { show: show, hide: hide, reload: loadAndRender };
})(window);
