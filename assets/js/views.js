(function (global) {
  "use strict";

  var VIEW_IDS = [
    "viewHome",
    "viewUsers",
    "viewNogas",
    "viewNogaCreate",
    "viewCities",
    "viewCityCreate",
    "viewTrubki",
    "viewTrubkaCreate",
    "viewTrubka",
    "viewProfile",
    "viewStats",
    "viewStatsTrubki",
    "viewChatRooms",
    "viewChatRoom",
  ];

  function show(id) {
    VIEW_IDS.forEach(function (viewId) {
      var el = document.getElementById(viewId);
      if (el) el.hidden = viewId !== id;
    });
    var screen = document.getElementById("appMain");
    if (screen) screen.scrollTop = 0;
  }

  function current() {
    for (var i = 0; i < VIEW_IDS.length; i++) {
      var el = document.getElementById(VIEW_IDS[i]);
      if (el && !el.hidden) return VIEW_IDS[i];
    }
    return null;
  }

  global.NogaViews = { show: show, current: current };
})(window);
