(function (global) {
  "use strict";

  var token = null;
  var onUnauthorized = null;

  function setToken(t) {
    token = t || null;
  }

  function getToken() {
    return token;
  }

  function setUnauthorizedHandler(fn) {
    onUnauthorized = fn;
  }

  function apiBase() {
    return (global.NOGA_CONFIG && global.NOGA_CONFIG.apiBase) || "";
  }

  function ApiError(status, code, message, body) {
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.message = message;
    this.body = body;
  }
  ApiError.prototype = Object.create(Error.prototype);

  async function request(path, options) {
    options = options || {};
    var headers = Object.assign({ Accept: "application/json" }, options.headers || {});
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    if (token && !options.skipAuth) {
      headers.Authorization = "Bearer " + token;
    }

    var res = await fetch(apiBase() + path, {
      method: options.method || "GET",
      headers: headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });

    var data = null;
    var text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (e) {
        data = { raw: text };
      }
    }

    if (res.status === 401 && onUnauthorized && !options.skipAuth) {
      onUnauthorized();
    }

    if (!res.ok) {
      var detail = (data && data.detail) || data || {};
      var code = detail.code || "HTTP_" + res.status;
      var message = detail.message || (typeof detail === "string" ? detail : res.statusText);
      throw new ApiError(res.status, code, message, data);
    }

    return data;
  }

  global.NogaApi = {
    setToken: setToken,
    getToken: getToken,
    setUnauthorizedHandler: setUnauthorizedHandler,
    request: request,
    ApiError: ApiError,
    authTelegram: function (initData) {
      return request("/api/auth/telegram", {
        method: "POST",
        skipAuth: true,
        body: { initData: initData },
      });
    },
    authDev: function (telegramId, secret) {
      return request("/api/auth/dev", {
        method: "POST",
        skipAuth: true,
        body: { telegram_id: Number(telegramId), secret: secret },
      });
    },
    me: function () {
      return request("/api/me");
    },
    dashboardSummary: function () {
      return request("/api/dashboard/summary");
    },
    listUsers: function () {
      return request("/api/users");
    },
    createUser: function (payload) {
      return request("/api/users", { method: "POST", body: payload });
    },
    updateUser: function (id, payload) {
      return request("/api/users/" + id, { method: "PATCH", body: payload });
    },
    deleteUser: function (id) {
      return request("/api/users/" + id, { method: "DELETE" });
    },
    listCities: function () {
      return request("/api/cities");
    },
    getCity: function (id) {
      return request("/api/cities/" + id);
    },
    createCity: function (payload) {
      return request("/api/cities", { method: "POST", body: payload });
    },
    updateCity: function (id, payload) {
      return request("/api/cities/" + id, { method: "PATCH", body: payload });
    },
    deleteCity: function (id) {
      return request("/api/cities/" + id, { method: "DELETE" });
    },
    listRazgruzy: function () {
      return request("/api/razgruzy");
    },
    createRazgruz: function (payload) {
      return request("/api/razgruzy", { method: "POST", body: payload });
    },
    updateRazgruz: function (id, payload) {
      return request("/api/razgruzy/" + id, { method: "PATCH", body: payload });
    },
    deleteRazgruz: function (id) {
      return request("/api/razgruzy/" + id, { method: "DELETE" });
    },
    listNogas: function () {
      return request("/api/nogas");
    },
    createNoga: function (payload) {
      return request("/api/nogas", { method: "POST", body: payload });
    },
    updateNoga: function (id, payload) {
      return request("/api/nogas/" + id, { method: "PATCH", body: payload });
    },
    deleteNoga: function (id) {
      return request("/api/nogas/" + id, { method: "DELETE" });
    },
  };
})(window);
