/* ============================================================
   EM 3.5 — Operations. Набор иконок
   Стиль снят с референса: monoline, одна толщина (1.6 при 24px),
   скруглённые окончания и стыки, без заливок — заливка только
   там, где она есть в макете (корона, звезда, точки статуса).
   Экспорт: window.EmIcons
     EmIcons.mount()          — вставляет спрайт в документ
     EmIcons.svg(name, cls)   — строка <svg><use/></svg>
     EmIcons.el(name, cls)    — готовый DOM-узел
     EmIcons.names()          — список имён
   ============================================================ */
(function (global) {
  "use strict";

  var S = 'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"';
  var F = 'fill="currentColor" stroke="none"';

  /* Каждая иконка — содержимое <symbol viewBox="0 0 24 24">.
     Логотип отдельным viewBox 48×60 — у гербового монограма пропорция 4:5. */
  var ICONS = {
    /* --- нижняя навигация ------------------------------------ */
    home: '<path ' + S + ' d="M4 10.8 12 4.4l8 6.4v8.4a1.6 1.6 0 0 1-1.6 1.6h-3.6v-5.6H9.2v5.6H5.6A1.6 1.6 0 0 1 4 19.2z"/>',
    doc: '<path ' + S + ' d="M7.2 3.4h6.1L18 8.1v12.5H7.2z"/><path ' + S + ' d="M13.1 3.5v4.7h4.8"/><path ' + S + ' d="M9.7 12.6h5.1M9.7 15.8h3.7"/>',
    plus: '<path ' + S + ' d="M12 5.2v13.6M5.2 12h13.6"/>',
    search: '<circle ' + S + ' cx="10.8" cy="10.8" r="6.2"/><path ' + S + ' d="m15.4 15.4 4.2 4.2"/>',
    profile: '<circle ' + S + ' cx="12" cy="12" r="8.4"/><circle ' + S + ' cx="12" cy="10.1" r="2.7"/><path ' + S + ' d="M6.7 18.5c1.2-2.1 3-3.2 5.3-3.2s4.1 1.1 5.3 3.2"/>',

    /* --- шапка и служебные ----------------------------------- */
    "chevron-left": '<path ' + S + ' d="M14.5 5.5 8 12l6.5 6.5"/>',
    "chevron-right": '<path ' + S + ' d="M9.5 5.5 16 12l-6.5 6.5"/>',
    "chevron-down": '<path ' + S + ' d="M5.5 9.5 12 16l6.5-6.5"/>',
    "chevron-up": '<path ' + S + ' d="M5.5 14.5 12 8l6.5 6.5"/>',
    dots: '<circle ' + F + ' cx="6" cy="12" r="1.5"/><circle ' + F + ' cx="12" cy="12" r="1.5"/><circle ' + F + ' cx="18" cy="12" r="1.5"/>',
    filter: '<path ' + S + ' d="M4 7.4h16M6.6 12h10.8M9.8 16.6h4.4"/>',
    bell: '<path ' + S + ' d="M17.8 16.4V11a5.8 5.8 0 1 0-11.6 0v5.4L4.6 18.4h14.8z"/><path ' + S + ' d="M9.9 21a2.4 2.4 0 0 0 4.2 0"/>',
    copy: '<rect ' + S + ' x="9" y="9" width="10.6" height="10.6" rx="2.4"/><path ' + S + ' d="M15.2 6.9V6.2a1.8 1.8 0 0 0-1.8-1.8H6.2A1.8 1.8 0 0 0 4.4 6.2v7.2a1.8 1.8 0 0 0 1.8 1.8h.7"/>',
    close: '<path ' + S + ' d="M6.4 6.4l11.2 11.2M17.6 6.4 6.4 17.6"/>',
    check: '<path ' + S + ' d="m5.2 12.6 4.6 4.6L18.8 7.4"/>',
    "check-circle": '<circle ' + S + ' cx="12" cy="12" r="8.4"/><path ' + S + ' d="m8.4 12.3 2.8 2.8 5.2-5.6"/>',
    "arrow-down-circle": '<circle ' + S + ' cx="12" cy="12" r="8.4"/><path ' + S + ' d="M12 7.8v8M8.8 12.6 12 15.8l3.2-3.2"/>',
    "pause-circle": '<circle ' + S + ' cx="12" cy="12" r="8.4"/><path ' + S + ' d="M10.3 9.2v5.6M13.7 9.2v5.6"/>',
    clock: '<circle ' + S + ' cx="12" cy="12" r="8.4"/><path ' + S + ' d="M12 7.4V12l3.2 1.9"/>',
    send: '<path ' + S + ' d="M20.4 3.6 10.2 13.8M20.4 3.6 14 20.4l-3.8-6.6-6.6-3.8z"/>',
    refresh: '<path ' + S + ' d="M19.8 12a7.8 7.8 0 1 1-2.3-5.5"/><path ' + S + ' d="M19.8 4.4V9h-4.6"/>',
    trash: '<path ' + S + ' d="M5.6 8h12.8M9.6 8V6.4A1.4 1.4 0 0 1 11 5h2a1.4 1.4 0 0 1 1.4 1.4V8"/><path ' + S + ' d="m7.6 8 .7 10.7a1.6 1.6 0 0 0 1.6 1.5h4.2a1.6 1.6 0 0 0 1.6-1.5L16.4 8"/>',
    pencil: '<path ' + S + ' d="M4.8 19.2h3.5L19.4 8.1a2.4 2.4 0 0 0-3.4-3.4L4.8 15.7z"/><path ' + S + ' d="m14.6 6.2 3.2 3.2"/>',
    download: '<path ' + S + ' d="M12 4.6v9.7M8.2 10.9 12 14.7l3.8-3.8M5 19.4h14"/>',
    camera: '<path ' + S + ' d="M4.4 8.9h2.9l1.4-2.3h6.6l1.4 2.3h2.9a1.6 1.6 0 0 1 1.6 1.6v7.3a1.6 1.6 0 0 1-1.6 1.6H4.4a1.6 1.6 0 0 1-1.6-1.6v-7.3a1.6 1.6 0 0 1 1.6-1.6z"/><circle ' + S + ' cx="12" cy="14.1" r="3.2"/>',
    eye: '<path ' + S + ' d="M2.8 12S6.4 6.5 12 6.5 21.2 12 21.2 12 17.6 17.5 12 17.5 2.8 12 2.8 12z"/><circle ' + S + ' cx="12" cy="12" r="2.9"/>',
    alert: '<path ' + S + ' d="M12 4.6 21 20H3z"/><path ' + S + ' d="M12 10v4.2"/><circle ' + F + ' cx="12" cy="17" r="1.1"/>',
    ruble: '<path ' + S + ' d="M9.4 19.4V5h4.2a4.3 4.3 0 0 1 0 8.6H9.4"/><path ' + S + ' d="M7 13.6h7.4"/>',
    dollar: '<path ' + S + ' d="M12 3.8v16.4"/><path ' + S + ' d="M15.8 7.6a3.4 3.4 0 0 0-3.4-2.2h-.6a3.2 3.2 0 0 0-.4 6.4h1.2a3.3 3.3 0 0 1 .3 6.6h-.7a3.5 3.5 0 0 1-3.5-2.3"/>',
    wallet: '<rect ' + S + ' x="3.4" y="6.6" width="17.2" height="12.4" rx="2.6"/><path ' + S + ' d="M3.4 10.4h17.2"/><circle ' + F + ' cx="16.6" cy="14.6" r="1.3"/>',
    banknote: '<rect ' + S + ' x="2.8" y="7" width="18.4" height="10" rx="2.2"/><circle ' + S + ' cx="12" cy="12" r="2.6"/><path ' + S + ' d="M6 12h.01M18 12h.01"/>',
    "map-pin": '<path ' + S + ' d="M12 20.8s6.2-5.7 6.2-10a6.2 6.2 0 1 0-12.4 0c0 4.3 6.2 10 6.2 10z"/><circle ' + S + ' cx="12" cy="10.6" r="2.4"/>',
    city: '<path ' + S + ' d="M4.4 20.4V10l5.6-2.7v3.3l5.4-2.6v12.4z"/><path ' + S + ' d="M15.4 12.6 20.6 15v5.4"/><path ' + S + ' d="M7.4 20.4v-3.2h2.4v3.2"/>',
    grid: '<rect ' + S + ' x="4.2" y="4.2" width="6.4" height="6.4" rx="1.6"/><rect ' + S + ' x="13.4" y="4.2" width="6.4" height="6.4" rx="1.6"/><rect ' + S + ' x="4.2" y="13.4" width="6.4" height="6.4" rx="1.6"/><rect ' + S + ' x="13.4" y="13.4" width="6.4" height="6.4" rx="1.6"/>',
    "card-live": '<rect ' + S + ' x="3.4" y="4.8" width="17.2" height="14.4" rx="2.6"/><path ' + S + ' d="M15.4 12a3.4 3.4 0 1 1-1-2.4"/><path ' + S + ' d="M14.9 6.9v2.7h-2.7"/>',
    bag: '<rect ' + S + ' x="3.4" y="7.8" width="17.2" height="11.6" rx="2.2"/><path ' + S + ' d="M9 7.8V6.4a1.6 1.6 0 0 1 1.6-1.6h2.8A1.6 1.6 0 0 1 15 6.4v1.4"/><path ' + S + ' d="M3.4 12.4h17.2"/>',
    box: '<path ' + S + ' d="M12 3.8 20.4 8v8L12 20.2 3.6 16V8z"/><path ' + S + ' d="M3.6 8 12 12.4 20.4 8M12 12.4v7.8"/>',
    calendar: '<rect ' + S + ' x="3.8" y="5.6" width="16.4" height="14.6" rx="2.4"/><path ' + S + ' d="M3.8 10h16.4M8.4 3.6v3.4M15.6 3.6v3.4"/>',
    upload: '<path ' + S + ' d="M12 15.4V5.8M8.2 9.6 12 5.8l3.8 3.8M5 19.4h14"/>',

    /* --- роли ------------------------------------------------- */
    crown: '<path ' + F + ' d="M4.2 18.2 3 8.6l5.2 3.8L12 5.6l3.8 6.8L21 8.6l-1.2 9.6z"/><path ' + S + ' d="M5 20.6h14"/>',
    star: '<path ' + F + ' d="m12 4.4 2.5 5.2 5.7.8-4.1 4 1 5.6-5.1-2.8-5.1 2.8 1-5.6-4.1-4 5.7-.8z"/>',
    shield: '<path ' + S + ' d="M12 3.6 5.4 6.1v5.7c0 4.1 2.7 7 6.6 8.4 3.9-1.4 6.6-4.3 6.6-8.4V6.1z"/><path ' + S + ' d="m9.4 12 2 2 3.2-3.4"/>',
    person: '<circle ' + S + ' cx="12" cy="8.2" r="3.4"/><path ' + S + ' d="M5.8 20c.9-3.4 3.3-5.1 6.2-5.1s5.3 1.7 6.2 5.1"/>',

    /* --- точки статуса (заливка) ----------------------------- */
    dot: '<circle ' + F + ' cx="12" cy="12" r="5"/>',
    "dot-ring": '<circle ' + S + ' stroke-width="2.6" cx="12" cy="12" r="5"/>'
  };

  /* Логотип EM: гербовый монограм. Геометрия снята с растра пиксельной картой
     яркости (см. README, раздел про логотип): три вложенные линии на каждую
     половину — внешняя нога с диагональю верхнего плеча, средняя и центральная
     стойка с шевроном по центру. Пропорция макета 120×150, поэтому viewBox
     48×60, а не квадрат. Металлическую фаску растра monoline не копирует. */
  var LOGO =
    '<symbol id="em-i-logo" viewBox="0 0 48 60">' +
    '<defs><linearGradient id="em-logo-grad" x1="0" y1="0" x2="1" y2="1">' +
    '<stop offset="0" stop-color="#FBEFD2"/><stop offset=".45" stop-color="#D9B26A"/><stop offset="1" stop-color="#A67C3E"/>' +
    "</linearGradient></defs>" +
    '<g fill="none" stroke="url(#em-logo-grad)" stroke-width="2.6" stroke-linejoin="miter" stroke-linecap="butt">' +
    /* внешние ноги: плечо от острого верхнего угла к центру, стойка, хвост вниз */
    '<path d="M19.6 23.4 2 3.5v38l19.4 17"/>' +
    '<path d="M28.4 23.4 46 3.5v38l-19.4 17"/>' +
    /* средняя линия — эхо внешней, ниже сходится в точку по центру */
    '<path d="M9.8 12.4V39l14.2 13 14.2-13V12.4" stroke-width="2.2"/>' +
    /* центральные стойки с шевроном: от них и читается M */
    '<path d="M19.6 1.6v21.8L24 28.4l4.4-5V1.6" stroke-width="2.2"/>' +
    "</g></symbol>";

  var MOUNT_ID = "em-icon-sprite";

  function spriteMarkup() {
    var out = '<svg id="' + MOUNT_ID + '" aria-hidden="true" focusable="false" style="position:absolute;width:0;height:0;overflow:hidden">';
    out += LOGO;
    Object.keys(ICONS).forEach(function (name) {
      out += '<symbol id="em-i-' + name + '" viewBox="0 0 24 24">' + ICONS[name] + "</symbol>";
    });
    return out + "</svg>";
  }

  function mount(doc) {
    doc = doc || global.document;
    if (!doc || doc.getElementById(MOUNT_ID)) return;
    var host = doc.createElement("div");
    host.innerHTML = spriteMarkup();
    var sprite = host.firstChild;
    doc.body.insertBefore(sprite, doc.body.firstChild);
  }

  function svg(name, cls) {
    var id = name === "logo" ? "em-i-logo" : "em-i-" + name;
    var box = name === "logo" ? "0 0 48 60" : "0 0 24 24";
    return (
      '<svg class="' + (cls || "") + '" viewBox="' + box + '" aria-hidden="true" focusable="false">' +
      '<use href="#' + id + '"/></svg>'
    );
  }

  function el(name, cls) {
    var box = global.document.createElement("div");
    box.innerHTML = svg(name, cls);
    return box.firstChild;
  }

  /* Разметка вида <span class="em-btn__icon" data-em-icon="home"></span>:
     <svg> вкладывается внутрь, сам слот остаётся на месте — иначе
     ломаются псевдоэлементы (золотая подложка активной вкладки)
     и вложенные размеры. Размер слота задаётся переменной
     --em-icon-size, она наследуется от компонента.
     data-em-title делает иконку доступной картинкой; без него
     она декоративная (aria-hidden). */
  function hydrate(root) {
    root = root || global.document;
    var nodes = root.querySelectorAll("[data-em-icon]");
    Array.prototype.forEach.call(nodes, function (node) {
      var name = node.getAttribute("data-em-icon");
      if (!ICONS[name] && name !== "logo") return;
      if (node.firstElementChild && node.firstElementChild.tagName.toLowerCase() === "svg") return;
      node.innerHTML = svg(name);
      var title = node.getAttribute("data-em-title");
      var mark = node.firstElementChild;
      if (title && mark) {
        mark.setAttribute("role", "img");
        mark.setAttribute("aria-label", title);
        mark.removeAttribute("aria-hidden");
      }
    });
  }

  global.EmIcons = {
    mount: mount,
    svg: svg,
    el: el,
    hydrate: hydrate,
    names: function () { return ["logo"].concat(Object.keys(ICONS)); }
  };
})(window);
