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
   * Админ и правая рука работают в справочниках, а не в операциях:
   * «Панель / Ноги / + / Города / Профиль» вместо «Главная / Операции / + / Поиск».
   */
  function applyTabbar() {
    var role = current && current.role;
    var workTabs = role === "admin" || role === "right_hand";

    var homeLabel = document.getElementById("tabHomeLabel");
    if (homeLabel) homeLabel.textContent = workTabs ? "Панель" : "Главная";

    setTabVisible("operations", !workTabs);
    setTabVisible("search", !workTabs);
    setTabVisible("nogas", workTabs && can("nogas:read"));
    setTabVisible("cities", workTabs && can("cities:read"));
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
