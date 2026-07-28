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

  function parseBody(text) {
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (e) {
      return { raw: text };
    }
  }

  function toApiError(res, data) {
    var detail = (data && data.detail) || data || {};
    var code = detail.code || "HTTP_" + res.status;
    var message = detail.message || (typeof detail === "string" ? detail : res.statusText);
    return new ApiError(res.status, code, message, data);
  }

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

    var data = parseBody(await res.text());

    if (res.status === 401 && onUnauthorized && !options.skipAuth) {
      onUnauthorized();
    }

    if (!res.ok) throw toApiError(res, data);

    return data;
  }

  /** Загрузка файла: Content-Type для multipart проставляет сам браузер. */
  async function upload(path, formData) {
    var headers = { Accept: "application/json" };
    if (token) headers.Authorization = "Bearer " + token;

    var res = await fetch(apiBase() + path, {
      method: "POST",
      headers: headers,
      body: formData,
    });

    var data = parseBody(await res.text());
    if (res.status === 401 && onUnauthorized) onUnauthorized();
    if (!res.ok) throw toApiError(res, data);
    return data;
  }

  /** Картинки и видео нельзя вставить в <img src>: токен уходит только в заголовке. */
  async function fetchBlob(path) {
    var headers = {};
    if (token) headers.Authorization = "Bearer " + token;

    var res = await fetch(apiBase() + path, { headers: headers });
    if (res.status === 401 && onUnauthorized) onUnauthorized();
    if (!res.ok) throw toApiError(res, parseBody(await res.text()));
    return await res.blob();
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
    /** Своё отображаемое имя; роль и статус этот запрос не меняет. */
    updateMe: function (payload) {
      return request("/api/me", { method: "PATCH", body: payload });
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
    /** scope: "own" — свой участок, "working" — общая витрина городов в работе. */
    listCities: function (scope) {
      return request("/api/cities" + (scope ? "?scope=" + scope : ""));
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
    /** detachNogas=true снимает прикреплённые ноги и всё-таки удаляет город. */
    deleteCity: function (id, options) {
      var query = options && options.detachNogas ? "?detach_nogas=true" : "";
      return request("/api/cities/" + id + query, { method: "DELETE" });
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
    deleteRazgruz: function (id, options) {
      var query = options && options.detachCities ? "?detach_cities=true" : "";
      return request("/api/razgruzy/" + id + query, { method: "DELETE" });
    },
    listNogas: function () {
      return request("/api/nogas");
    },
    getNoga: function (id) {
      return request("/api/nogas/" + id);
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
    uploadNogaFile: function (nogaId, kind, file) {
      var form = new FormData();
      form.append("kind", kind);
      form.append("file", file, file.name);
      return upload("/api/nogas/" + nogaId + "/files", form);
    },
    nogaFileBlob: function (nogaId, fileId) {
      return fetchBlob("/api/nogas/" + nogaId + "/files/" + fileId);
    },
    deleteNogaFile: function (nogaId, fileId) {
      return request("/api/nogas/" + nogaId + "/files/" + fileId, { method: "DELETE" });
    },
  };
})(window);
