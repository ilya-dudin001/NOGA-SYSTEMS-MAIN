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

  function queryString(params) {
    var query = [];
    Object.keys(params || {}).forEach(function (key) {
      var value = params[key];
      if (value === null || value === undefined || value === "") return;
      query.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
    });
    return query.length ? "?" + query.join("&") : "";
  }

  /** Multipart чата через XHR: Promise дополнен abort(). */
  function sendChatMessage(roomId, content, replyToId, files, onProgress) {
    var xhr = new XMLHttpRequest();
    var form = new FormData();
    form.append("content", JSON.stringify(content || []));
    if (replyToId !== null && replyToId !== undefined) {
      form.append("reply_to_id", String(replyToId));
    }
    Array.prototype.forEach.call(files || [], function (file) {
      form.append("files", file, file.name);
    });

    var promise = new Promise(function (resolve, reject) {
      xhr.open("POST", apiBase() + "/api/chat/rooms/" + roomId + "/messages");
      xhr.setRequestHeader("Accept", "application/json");
      if (token) xhr.setRequestHeader("Authorization", "Bearer " + token);
      if (xhr.upload && onProgress) {
        xhr.upload.onprogress = function (event) {
          onProgress({
            loaded: event.loaded || 0,
            total: event.total || 0,
            percent: event.lengthComputable && event.total
              ? Math.round((event.loaded / event.total) * 100)
              : null,
          });
        };
      }
      xhr.onload = function () {
        var data = parseBody(xhr.responseText);
        if (xhr.status === 401 && onUnauthorized) onUnauthorized();
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(toApiError(xhr, data));
          return;
        }
        resolve(data);
      };
      xhr.onerror = function () {
        reject(new ApiError(0, "NETWORK_ERROR", "Не удалось отправить сообщение", null));
      };
      xhr.onabort = function () {
        var error = new Error("Загрузка отменена");
        error.name = "AbortError";
        reject(error);
      };
      xhr.send(form);
    });
    promise.abort = function () {
      xhr.abort();
    };
    return promise;
  }

  function createSseParser(onEvent) {
    var buffer = "";
    var frame = { id: null, event: "message", data: [] };

    function dispatch() {
      if (!frame.data.length) {
        frame = { id: null, event: "message", data: [] };
        return;
      }
      var raw = frame.data.join("\n");
      var data;
      try {
        data = JSON.parse(raw);
      } catch (e) {
        data = raw;
      }
      onEvent({
        id: frame.id,
        event: frame.event || "message",
        data: data,
      });
      frame = { id: null, event: "message", data: [] };
    }

    function line(value) {
      if (value === "") {
        dispatch();
        return;
      }
      if (value.charAt(0) === ":") return;
      var colon = value.indexOf(":");
      var field = colon === -1 ? value : value.slice(0, colon);
      var fieldValue = colon === -1 ? "" : value.slice(colon + 1);
      if (fieldValue.charAt(0) === " ") fieldValue = fieldValue.slice(1);
      if (field === "id") frame.id = fieldValue;
      if (field === "event") frame.event = fieldValue;
      if (field === "data") frame.data.push(fieldValue);
    }

    return {
      push: function (chunk) {
        buffer += String(chunk || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
        var index;
        while ((index = buffer.indexOf("\n")) !== -1) {
          line(buffer.slice(0, index));
          buffer = buffer.slice(index + 1);
        }
      },
      finish: function () {
        if (buffer) line(buffer);
        buffer = "";
        dispatch();
      },
    };
  }

  /**
   * Durable SSE через fetch + ReadableStream.
   * options: roomId, lastEventId, onEvent, onError, onState, reconnectDelays.
   */
  function openChatStream(options) {
    options = options || {};
    var aborted = false;
    var controller = null;
    var timer = null;
    var cursor = options.lastEventId;
    var attempt = 0;
    var delays = options.reconnectDelays || [1000, 2000, 5000, 10000, 30000];

    function state(value) {
      if (options.onState) options.onState(value);
    }

    function delayForAttempt() {
      var index = Math.min(attempt, delays.length - 1);
      var delay = Number(delays[index] || 0);
      if (attempt >= delays.length && delay > 0) {
        delay = Math.round(delay * (0.8 + Math.random() * 0.4));
      }
      attempt += 1;
      return delay;
    }

    function schedule() {
      if (aborted || timer) return;
      state("reconnecting");
      timer = setTimeout(function () {
        timer = null;
        connect();
      }, delayForAttempt());
    }

    async function connect() {
      if (aborted) return;
      controller = new AbortController();
      var headers = { Accept: "text/event-stream" };
      if (token) headers.Authorization = "Bearer " + token;
      if (cursor !== null && cursor !== undefined && cursor !== "") {
        headers["Last-Event-ID"] = String(cursor);
      }
      var path = "/api/chat/stream" + queryString({ room_id: options.roomId });
      state("connecting");
      try {
        var response = await fetch(apiBase() + path, {
          headers: headers,
          signal: controller.signal,
          cache: "no-store",
        });
        if (response.status === 401) {
          aborted = true;
          if (onUnauthorized) onUnauthorized();
          state("unauthorized");
          return;
        }
        if (response.status === 403) {
          aborted = true;
          if (options.onError) {
            options.onError(toApiError(response, parseBody(await response.text())));
          }
          state("forbidden");
          return;
        }
        if (!response.ok) {
          throw toApiError(response, parseBody(await response.text()));
        }
        if (!response.body || !response.body.getReader) {
          throw new Error("ReadableStream недоступен");
        }

        state("open");
        attempt = 0;
        var reader = response.body.getReader();
        var decoder = new TextDecoder("utf-8");
        var parser = createSseParser(function (frame) {
          if (frame.id !== null && frame.id !== "") cursor = frame.id;
          if (frame.data && frame.data.event_id !== null && frame.data.event_id !== undefined) {
            cursor = frame.data.event_id;
          }
          if (options.onEvent) options.onEvent(frame.data, frame);
        });
        while (!aborted) {
          var part = await reader.read();
          if (part.done) break;
          parser.push(decoder.decode(part.value, { stream: true }));
        }
        parser.push(decoder.decode());
        parser.finish();
        if (!aborted) schedule();
      } catch (error) {
        if (aborted || (error && error.name === "AbortError")) return;
        if (options.onError) options.onError(error);
        schedule();
      }
    }

    function reconnectNow() {
      if (aborted) return;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      if (controller) controller.abort();
      connect();
    }

    function onOnline() {
      reconnectNow();
    }

    function onVisibility() {
      if (document.visibilityState === "visible") reconnectNow();
    }

    global.addEventListener("online", onOnline);
    document.addEventListener("visibilitychange", onVisibility);
    connect();

    return {
      abort: function () {
        aborted = true;
        if (timer) clearTimeout(timer);
        timer = null;
        if (controller) controller.abort();
        global.removeEventListener("online", onOnline);
        document.removeEventListener("visibilitychange", onVisibility);
        state("closed");
      },
      getLastEventId: function () {
        return cursor;
      },
    };
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
    /** Подсказки названия города и валюта страны (опечатки → Photon). */
    suggestCities: function (query, limit, lang) {
      var q = encodeURIComponent(query || "");
      var lim = limit ? "&limit=" + Number(limit) : "";
      var locale =
        lang ||
        (global.NogaTelegram && global.NogaTelegram.getUiLang
          ? global.NogaTelegram.getUiLang()
          : "ru");
      return request(
        "/api/cities/suggest?q=" + q + lim + "&lang=" + encodeURIComponent(locale)
      );
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
    /** params: { status, city_id, limit, offset, include_reported, with_total } */
    listTrubki: function (params) {
      var query = [];
      Object.keys(params || {}).forEach(function (key) {
        var value = params[key];
        if (value === null || value === undefined || value === "") return;
        if (value === false) return;
        query.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
      });
      return request("/api/trubki" + (query.length ? "?" + query.join("&") : ""));
    },
    /** Полный архив с total — для статистики. */
    listTrubkiPage: function (params) {
      var options = Object.assign({ include_reported: true, with_total: true }, params || {});
      return this.listTrubki(options);
    },
    getTrubka: function (id) {
      return request("/api/trubki/" + id);
    },
    createTrubka: function (payload) {
      return request("/api/trubki", { method: "POST", body: payload });
    },
    updateTrubka: function (id, payload) {
      return request("/api/trubki/" + id, { method: "PATCH", body: payload });
    },
    setTrubkaRecalculation: function (id, amount) {
      return request("/api/trubki/" + id + "/recalculation", {
        method: "POST",
        body: { amount: Number(amount) },
      });
    },
    setTrubkaUsdt: function (id, amount) {
      return request("/api/trubki/" + id + "/usdt", {
        method: "POST",
        body: { amount: Number(amount) },
      });
    },
    sendTrubkaReport: function (id) {
      return request("/api/trubki/" + id + "/report", { method: "POST" });
    },
    uploadTrubkaFile: function (id, kind, file) {
      var form = new FormData();
      form.append("kind", kind);
      form.append("file", file, file.name);
      return upload("/api/trubki/" + id + "/files", form);
    },
    trubkaFileBlob: function (id, fileId) {
      return fetchBlob("/api/trubki/" + id + "/files/" + fileId);
    },
    deleteTrubka: function (id) {
      return request("/api/trubki/" + id, { method: "DELETE" });
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
    chatRooms: function () {
      return request("/api/chat/rooms");
    },
    chatPeers: function () {
      return request("/api/chat/peers");
    },
    createChatDirect: function (peerUserId) {
      return request("/api/chat/direct", {
        method: "POST",
        body: { peer_user_id: Number(peerUserId) },
      });
    },
    chatMessages: function (roomId, params) {
      return request("/api/chat/rooms/" + roomId + "/messages" + queryString(params));
    },
    sendChatMessage: sendChatMessage,
    deleteChatMessage: function (messageId) {
      return request("/api/chat/messages/" + messageId, { method: "DELETE" });
    },
    updateChatRead: function (roomId, messageId) {
      return request("/api/chat/rooms/" + roomId + "/read", {
        method: "PATCH",
        body: { last_read_message_id: Number(messageId) },
      });
    },
    chatMentions: function (unreadOnly, limit) {
      return request(
        "/api/chat/mentions" +
          queryString({ unread_only: unreadOnly ? "true" : "", limit: limit })
      );
    },
    readChatMention: function (mentionId) {
      return request("/api/chat/mentions/" + mentionId + "/read", { method: "PATCH" });
    },
    chatAttachmentBlob: function (attachmentId) {
      return fetchBlob("/api/chat/attachments/" + attachmentId);
    },
    openChatStream: openChatStream,
    createSseParser: createSseParser,
    /** Поиск банкоматов / терминалов / крупных POI рядом с адресом. */
    placesNearby: function (payload) {
      return request("/api/places/nearby", { method: "POST", body: payload });
    },
  };
})(window);
