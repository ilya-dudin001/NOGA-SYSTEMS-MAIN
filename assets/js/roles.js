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

  /** Which bottom tabs are visible for this role */
  function visibleTabs() {
    var tabs = ["home", "operations", "search", "profile"];
    if (can("users:manage") || can("users:read")) {
      /* users screen opened from profile / dedicated nav later */
    }
    return tabs;
  }

  global.NogaRoles = {
    setUser: setUser,
    getUser: getUser,
    can: can,
    roleLabel: roleLabel,
    visibleTabs: visibleTabs,
  };
})(window);
