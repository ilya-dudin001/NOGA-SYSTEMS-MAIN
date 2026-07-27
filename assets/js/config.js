/* NOGA Mini App — runtime config.
   Override via window.__NOGA_CONFIG__ before this script, or query ?api=https://host */
(function (global) {
  "use strict";

  var params = new URLSearchParams(global.location.search);
  var fromQuery = params.get("api");
  var defaults = {
    apiBase: "http://127.0.0.1:8000",
    // Dev login form when Telegram.WebApp.initData is missing
    allowDevLogin: true,
  };

  var config = Object.assign({}, defaults, global.__NOGA_CONFIG__ || {});
  if (fromQuery) config.apiBase = fromQuery;

  global.NOGA_CONFIG = config;
})(window);
