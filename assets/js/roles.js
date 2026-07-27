(function (global) {
  "use strict";

  var current = null;

  function setUser(user) {
    current = user;
  }

  function getUser() {
    return current;
  }

  function can(permission) {
    if (!current || !current.permissions) return false;
    return current.permissions.indexOf(permission) !== -1;
  }

  function roleLabel() {
    return (current && current.role_label) || (current && current.role) || "";
  }

  function tabNode(name) {
    return document.querySelector('.tab[data-tab="' + name + '"]');
  }

  function setTabVisible(name, visible) {
    var node = tabNode(name);
    if (node) node.hidden = !visible;
  }

  /**
   * Таббар: «Панель / Ноги / + / Города / Профиль».
   * Ноги и города видны по правам; без права ячейка остаётся пустой, чтобы «+» не съезжал.
   */
  function applyTabbar() {
    var homeLabel = document.getElementById("tabHomeLabel");
    if (homeLabel) homeLabel.textContent = "Панель";

    setTabVisible("nogas", can("nogas:read"));
    setTabVisible("cities", can("cities:read"));
  }

  /** Подсвечивает вкладку; если её нет в таббаре — подсвечивает «Профиль». */
  function activateTab(name) {
    var node = tabNode(name);
    var target = node && !node.hidden ? node : tabNode("profile");
    if (!target) return;
    Array.prototype.forEach.call(document.querySelectorAll(".tab[data-tab]"), function (tab) {
      tab.classList.remove("is-active");
      tab.removeAttribute("aria-current");
    });
    target.classList.add("is-active");
    target.setAttribute("aria-current", "page");
  }

  global.NogaRoles = {
    setUser: setUser,
    getUser: getUser,
    can: can,
    roleLabel: roleLabel,
    applyTabbar: applyTabbar,
    activateTab: activateTab,
  };
})(window);
