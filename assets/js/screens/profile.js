/* Профиль: карточка текущего пользователя и вход в его разделы. */
(function (global) {
  "use strict";

  var ICONS = {
    users:
      '<circle cx="9" cy="8" r="3.2"/>' +
      '<path d="M3 20v-1.6A4.4 4.4 0 0 1 7.4 14h3.2a4.4 4.4 0 0 1 4.4 4.4V20"/>' +
      '<path d="M16.4 5.3a3.2 3.2 0 0 1 0 5.4"/>' +
      '<path d="M18.2 14.3A4.4 4.4 0 0 1 21 18.4V20"/>',
    cities:
      '<path d="M3 21h18"/>' +
      '<path d="M5 21V9l5-3.5V21"/>' +
      '<path d="M14 21V11h5v10"/>' +
      '<path d="M7.6 12h.01M7.6 15.5h.01M16.4 14.5h.01M16.4 17.5h.01"/>',
    nogas:
      '<circle cx="12" cy="7" r="3.2"/>' +
      '<path d="M6 21v-2.2A4.8 4.8 0 0 1 10.8 14h2.4A4.8 4.8 0 0 1 18 18.8V21"/>',
    razgruzy:
      '<path d="M4 8.5h13"/><path d="m14 5.5 3 3-3 3"/>' +
      '<path d="M20 15.5H7"/><path d="m10 12.5-3 3 3 3"/>',
    trubki:
      '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h2.2c.7 0 1.3.5 1.5 1.2l.7 2.6c.1.6-.1 1.2-.6 1.5' +
      'l-1.4 1a12 12 0 0 0 5.8 5.8l1-1.4c.4-.5 1-.7 1.6-.6l2.6.7c.7.2 1.2.8 1.2 1.5v2.2' +
      'a1.5 1.5 0 0 1-1.5 1.5A15.5 15.5 0 0 1 4 5.5Z"/>',
    stats:
      '<path d="M3.5 20.5h17"/>' +
      '<path d="M6.5 17.5v-5"/><path d="M12 17.5v-10"/><path d="M17.5 17.5v-7"/>',
    chevron: '<path d="m9 6 6 6-6 6"/>',
  };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function svgIcon(icon) {
    return (
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      ICONS[icon] +
      "</svg>"
    );
  }

  function can(permission) {
    return global.NogaRoles.can(permission);
  }

  /** Инициалы для аватара: «Иван Петров» → «ИП». */
  function initials(name) {
    var parts = String(name || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!parts.length) return "?";
    var first = parts[0].charAt(0);
    var second = parts.length > 1 ? parts[1].charAt(0) : "";
    return (first + second).toUpperCase();
  }

  function addRow(list, key, value) {
    if (!value) return;
    var row = el("div", "profile-card__row");
    row.appendChild(el("dt", "profile-card__key", key));
    row.appendChild(el("dd", "profile-card__value", value));
    list.appendChild(row);
  }

  function renderCard(user) {
    var avatar = document.getElementById("profileAvatar");
    var name = document.getElementById("profileName");
    var role = document.getElementById("profileRole");
    var rows = document.getElementById("profileRows");
    if (!rows) return;

    if (avatar) avatar.textContent = initials(user.display_name);
    if (name) name.textContent = user.display_name || "—";
    if (role) role.textContent = user.role_label || user.role || "";

    var renameBtn = document.getElementById("profileRenameBtn");
    if (renameBtn) renameBtn.hidden = !can("profile:rename");

    rows.innerHTML = "";
    addRow(rows, "Telegram ID", String(user.telegram_id));
    addRow(rows, "Username", user.username ? "@" + user.username : "");
    addRow(rows, "Статус", user.status === "blocked" ? "Заблокирован" : "Активен");
    addRow(rows, "В системе с", global.NogaDict.formatDate(user.created_at));
    if (user.last_seen_at) {
      addRow(rows, "Последний вход", global.NogaDict.formatDate(user.last_seen_at));
    }
  }

  /* ---------- детали под дропдауном ---------- */

  function setDetails(open) {
    var toggle = document.getElementById("profileDetailsToggle");
    var rows = document.getElementById("profileRows");
    if (!toggle || !rows) return;
    rows.hidden = !open;
    toggle.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  /* ---------- свой ник ---------- */

  // Те же правила, что и на сервере (services/users.normalize_display_name):
  // кириллица, латиница и цифры, между ними пробел, дефис или подчёркивание.
  var NICK_RE = /^[А-Яа-яЁёA-Za-z0-9]+([ _-][А-Яа-яЁёA-Za-z0-9]+)*$/;
  var NICK_HINT =
    "Ник может состоять из русских и английских букв, цифр, пробела, дефиса и подчёркивания";

  function openRename(user) {
    var form = document.getElementById("profileRenameForm");
    var input = document.getElementById("profileNick");
    var btn = document.getElementById("profileRenameBtn");
    if (!form || !input) return;
    input.value = user.display_name || "";
    form.hidden = false;
    if (btn) btn.hidden = true;
    input.focus();
  }

  function closeRename() {
    var form = document.getElementById("profileRenameForm");
    var btn = document.getElementById("profileRenameBtn");
    if (form) form.hidden = true;
    if (btn) btn.hidden = !can("profile:rename");
  }

  async function saveNick() {
    var input = document.getElementById("profileNick");
    if (!input) return;
    var value = input.value.replace(/\s+/g, " ").trim();
    if (value.length < 2 || value.length > 32) {
      global.NogaTelegram.notify("Ник должен быть от 2 до 32 символов");
      return;
    }
    if (!NICK_RE.test(value)) {
      global.NogaTelegram.notify(NICK_HINT);
      return;
    }
    try {
      var updated = await global.NogaApi.updateMe({ display_name: value });
      // Права и роль перечитываются с сервера — приветствие на дашборде тоже обновляем.
      global.NogaRoles.setUser(updated);
      global.NogaDashboard.applyUser(updated);
      closeRename();
      renderCard(updated);
    } catch (err) {
      global.NogaTelegram.notify(err.message || "Не удалось сохранить ник");
    }
  }

  var cardBound = false;

  function bindCard() {
    if (cardBound) return;
    cardBound = true;

    var toggle = document.getElementById("profileDetailsToggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        setDetails(document.getElementById("profileRows").hidden);
      });
    }

    var renameBtn = document.getElementById("profileRenameBtn");
    if (renameBtn) {
      renameBtn.addEventListener("click", function () {
        var user = global.NogaRoles.getUser();
        if (user) openRename(user);
      });
    }

    var cancel = document.getElementById("profileRenameCancel");
    if (cancel) cancel.addEventListener("click", closeRename);

    var form = document.getElementById("profileRenameForm");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        saveNick();
      });
    }
  }

  /**
   * Разделы профиля. У роли noga их нет — ей остаётся только карточка:
   * ни ног, ни разгрузов, ни общей статистики она не видит.
   * Пользователи здесь у тех, кто ими управляет; админу список доступен
   * только с дашборда — править он его всё равно не может.
   */
  function menuItems(user) {
    var items = [];

    if (can("users:manage")) {
      items.push({
        icon: "users",
        label: "Пользователи",
        view: "viewUsers",
        open: function () {
          global.NogaUsers.show();
        },
      });
    }

    if (user.role === "noga") return items;

    items.push({
      icon: "trubki",
      label: "Трубки",
      view: "viewTrubki",
      open: function () {
        global.NogaTrubki.show({ status: "" });
      },
    });

    if (can("cities:read")) {
      items.push({
        icon: "cities",
        label: can("cities:all") ? "Города" : "Мои города",
        view: "viewCities",
        open: function () {
          global.NogaCities.show({ mode: "own" });
        },
      });
    }

    if (can("nogas:read")) {
      items.push({
        icon: "nogas",
        label: can("nogas:all") ? "Ноги" : "Мои ноги",
        view: "viewNogas",
        open: function () {
          global.NogaNogas.show();
        },
      });
    }

    if (can("razgruz:read")) {
      items.push({
        icon: "razgruzy",
        label: can("razgruz:all") ? "Разгрузы" : "Мои разгрузы",
        view: "viewRazgruzy",
        open: function () {
          global.NogaRazgruzy.show({ mine: true });
        },
      });
    }

    items.push({
      icon: "stats",
      label: "Статистика",
      view: "viewStats",
      open: function () {
        global.NogaStats.show();
      },
    });

    return items;
  }

  /**
   * Кнопка возврата живёт в шапке каждого раздела и показывается только тогда,
   * когда в раздел пришли из профиля: с дашборда и из таббара возвращаться некуда.
   */
  function backButtons() {
    return document.querySelectorAll(".btn-back");
  }

  function showBack(viewId) {
    Array.prototype.forEach.call(backButtons(), function (btn) {
      btn.hidden = btn.getAttribute("data-back") !== viewId;
    });
  }

  function hideBack() {
    showBack(null);
  }

  var backBound = false;

  function bindBack() {
    if (backBound) return;
    backBound = true;
    Array.prototype.forEach.call(backButtons(), function (btn) {
      btn.addEventListener("click", show);
    });
  }

  function buildMenuItem(item) {
    var btn = el("button", "profile-menu__item");
    btn.type = "button";

    var icon = el("span", "profile-menu__icon");
    icon.innerHTML = svgIcon(item.icon);
    btn.appendChild(icon);

    btn.appendChild(el("span", "profile-menu__label", item.label));

    var chevron = el("span", "profile-menu__chevron");
    chevron.innerHTML = svgIcon("chevron");
    btn.appendChild(chevron);

    btn.addEventListener("click", function () {
      item.open();
      showBack(item.view);
    });
    return btn;
  }

  function renderMenu(user) {
    var menu = document.getElementById("profileMenu");
    if (!menu) return;
    menu.innerHTML = "";

    var items = menuItems(user);
    if (!items.length) {
      menu.appendChild(el("p", "empty-hint", "Дополнительных разделов у вашей роли нет"));
      return;
    }
    items.forEach(function (item) {
      menu.appendChild(buildMenuItem(item));
    });
  }

  function show() {
    var user = global.NogaRoles.getUser();
    if (!user) return;
    // Уходим с экрана ног — их предпросмотры держат blob-ссылки.
    global.NogaNogas.release();
    bindBack();
    hideBack();
    bindCard();
    closeRename();
    setDetails(false);
    global.NogaViews.show("viewProfile");
    renderCard(user);
    renderMenu(user);
  }

  global.NogaProfile = { show: show, hideBack: hideBack };
})(window);
