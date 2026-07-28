/* Вылетающее меню создания на кнопке «+» в центре таббара. */
(function (global) {
  "use strict";

  var ICONS = {
    trubka:
      '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h2.2c.7 0 1.3.5 1.5 1.2l.7 2.6c.1.6-.1 1.2-.6 1.5l-1.4 1a12 12 0 0 0 5.8 5.8l1-1.4c.4-.5 1-.7 1.6-.6l2.6.7c.7.2 1.2.8 1.2 1.5v2.2a1.5 1.5 0 0 1-1.5 1.5A15.5 15.5 0 0 1 4 5.5Z"/>',
    city:
      '<path d="M3 21h18"/><path d="M5 21V9l5-3.5V21"/><path d="M14 21V11h5v10"/>' +
      '<path d="M7.6 12h.01M7.6 15.5h.01M16.4 14.5h.01M16.4 17.5h.01"/>',
    noga:
      '<circle cx="12" cy="7" r="3.2"/>' +
      '<path d="M6 21v-2.2A4.8 4.8 0 0 1 10.8 14h2.4A4.8 4.8 0 0 1 18 18.8V21"/>',
    razgruz:
      '<path d="M4 8.5h13"/><path d="m14 5.5 3 3-3 3"/>' +
      '<path d="M20 15.5H7"/><path d="m10 12.5-3 3 3 3"/>',
  };

  var bound = false;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function can(permission) {
    return global.NogaRoles.can(permission);
  }

  /** Что вообще можно создать этой роли. Пустой список — меню не открываем. */
  function items() {
    var list = [];
    if (can("operations:all")) {
      list.push({
        icon: "trubka",
        label: "Трубка",
        open: function () {
          return global.NogaTrubki.openCreate();
        },
      });
    }
    if (can("cities:manage")) {
      list.push({
        icon: "city",
        label: "Город",
        open: function () {
          return global.NogaCities.openCreate();
        },
      });
    }
    if (can("nogas:manage")) {
      list.push({
        icon: "noga",
        label: "Нога",
        open: function () {
          return global.NogaNogas.openCreate();
        },
      });
    }
    if (can("razgruz:manage")) {
      list.push({
        icon: "razgruz",
        label: "Разгруз",
        open: function () {
          return global.NogaRazgruzy.openCreate();
        },
      });
    }
    return list;
  }

  function buildItem(item, index, total) {
    var btn = el("button", "fab-menu__item");
    btn.type = "button";
    btn.setAttribute("role", "menuitem");
    // Верхний пункт появляется последним: список «вырастает» из кнопки «+».
    btn.style.transitionDelay = (total - index - 1) * 40 + "ms";

    btn.appendChild(el("span", "fab-menu__label", item.label));

    var icon = el("span", "fab-menu__icon");
    icon.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      ICONS[item.icon] +
      "</svg>";
    btn.appendChild(icon);

    btn.addEventListener("click", function () {
      close();
      global.NogaProfile.hideBack();
      item.open();
    });
    return btn;
  }

  function render() {
    var list = document.getElementById("fabMenuList");
    if (!list) return 0;
    list.innerHTML = "";
    var entries = items();
    entries.forEach(function (item, index) {
      list.appendChild(buildItem(item, index, entries.length));
    });
    return entries.length;
  }

  function isOpen() {
    var menu = document.getElementById("fabMenu");
    return Boolean(menu && !menu.hidden);
  }

  function open() {
    var menu = document.getElementById("fabMenu");
    var fab = document.getElementById("fab");
    if (!menu) return;
    if (!render()) {
      global.NogaTelegram.notify("У вашей роли нет разделов для создания");
      return;
    }
    menu.hidden = false;
    // Класс вешаем следующим кадром: иначе переход стартует с конечного состояния.
    requestAnimationFrame(function () {
      menu.classList.add("is-open");
    });
    if (fab) {
      fab.classList.add("is-open");
      fab.setAttribute("aria-expanded", "true");
    }
  }

  function close() {
    var menu = document.getElementById("fabMenu");
    var fab = document.getElementById("fab");
    if (!menu || menu.hidden) return;
    menu.classList.remove("is-open");
    if (fab) {
      fab.classList.remove("is-open");
      fab.setAttribute("aria-expanded", "false");
    }
    var hide = function () {
      menu.hidden = true;
    };
    // Ждём затухание, но не полагаемся на transitionend: он не придёт, если
    // анимации выключены системной настройкой.
    setTimeout(hide, 220);
  }

  function toggle() {
    if (isOpen()) {
      close();
    } else {
      open();
    }
  }

  function bind() {
    if (bound) return;
    bound = true;

    var fab = document.getElementById("fab");
    if (fab) fab.addEventListener("click", toggle);

    var backdrop = document.getElementById("fabBackdrop");
    if (backdrop) backdrop.addEventListener("click", close);

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
  }

  global.NogaCreateMenu = { bind: bind, open: open, close: close, toggle: toggle };
})(window);
