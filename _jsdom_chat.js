/* Этап 6: feature gate, rooms shell, SSE parser/reconnect, unauthorized cleanup. */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const root = __dirname;
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost/" });
const { window } = dom;

window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {} });
window.Element.prototype.scrollIntoView = function () {};
window.URL.createObjectURL = () => "blob:fake";
window.URL.revokeObjectURL = () => {};
window.requestAnimationFrame = (callback) => setTimeout(() => callback(Date.now()), 0);
window.TextEncoder = global.TextEncoder;
window.TextDecoder = global.TextDecoder;

const calls = [];
const streamControllers = [];
let roomsPayload = {
  latest_event_id: 10,
  total_unread: 2,
  total_unread_mentions: 1,
  rooms: [
    {
      id: 1,
      kind: "system",
      slug: "general",
      title: "Общий",
      peer: null,
      unread_count: 2,
      unread_mentions: 1,
      last_message: {
        id: 50,
        author_name: "Иван",
        preview: "Проверьте документ",
        has_attachments: false,
        created_at: "2026-08-01T12:00:00Z",
      },
    },
    {
      id: 2,
      kind: "system",
      slug: "alerts",
      title: "Алерты",
      peer: null,
      unread_count: 0,
      unread_mentions: 0,
      last_message: null,
    },
    {
      id: 18,
      kind: "direct",
      slug: null,
      title: "Мария",
      peer: { id: 12, display_name: "Мария", username: "maria", role: "admin" },
      unread_count: 0,
      unread_mentions: 0,
      last_message: {
        id: 51,
        author_name: "Мария",
        preview: "Ок",
        has_attachments: false,
        created_at: "2026-08-01T11:00:00Z",
      },
    },
  ],
};

function response(data, status = 200, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    headers: {
      get: (name) => headers[String(name).toLowerCase()] || null,
    },
    text: async () => (data === null ? "" : typeof data === "string" ? data : JSON.stringify(data)),
    blob: async () => new window.Blob(["x"], { type: "application/octet-stream" }),
    json: async () => data,
    body: null,
  };
}

function streamResponse(chunks, status = 200) {
  let index = 0;
  const encoder = new TextEncoder();
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    headers: { get: () => null },
    text: async () => "",
    body: {
      getReader() {
        const ctrl = { aborted: false };
        streamControllers.push(ctrl);
        return {
          async read() {
            if (ctrl.aborted || index >= chunks.length) {
              return { done: true, value: undefined };
            }
            const value = chunks[index++];
            return {
              done: false,
              value: typeof value === "string" ? encoder.encode(value) : value,
            };
          },
          cancel() {
            ctrl.aborted = true;
          },
        };
      },
    },
  };
}

window.fetch = async (url, options = {}) => {
  const method = options.method || "GET";
  calls.push({
    url: String(url),
    method,
    headers: options.headers || {},
    signal: options.signal,
  });

  if (String(url).includes("/api/chat/stream")) {
    if (options.signal && options.signal.aborted) {
      const err = new Error("Aborted");
      err.name = "AbortError";
      throw err;
    }
    // Долгий «тихий» stream: без бизнес-событий, чтобы unread из REST не съезжал.
    return {
      ok: true,
      status: 200,
      statusText: "OK",
      headers: { get: () => null },
      text: async () => "",
      body: {
        getReader() {
          const ctrl = { aborted: false };
          streamControllers.push(ctrl);
          if (options.signal) {
            options.signal.addEventListener("abort", () => {
              ctrl.aborted = true;
            });
          }
          return {
            async read() {
              if (ctrl.aborted) return { done: true, value: undefined };
              await new Promise((resolve) => setTimeout(resolve, 200));
              if (ctrl.aborted) return { done: true, value: undefined };
              return { done: false, value: new TextEncoder().encode(": heartbeat\n\n") };
            },
            cancel() {
              ctrl.aborted = true;
            },
          };
        },
      },
    };
  }

  if (String(url).includes("/api/chat/rooms")) return response(roomsPayload);
  if (String(url).includes("/api/dashboard/summary")) {
    return response({
      turnover_rub: 0,
      turnover_usd: 0,
      scope: "global",
      cities: { total: 0, working: 0, paused: 0, stopped: 0, nogas: 0, razgruzy: 0 },
      trubki: { total: 0, zacep: 0, zabrali: 0, razgruzhaetsya: 0, vyplacheno: 0, srez: 0 },
    });
  }
  return response({});
};

[
  "design-system/icons.js",
  "design-system/ds.js",
  "assets/js/config.js",
  "assets/js/telegram.js",
  "assets/js/api.js",
  "assets/js/roles.js",
  "assets/js/dict.js",
  "assets/js/views.js",
  "assets/js/screens/dashboard.js",
  "assets/js/screens/no-access.js",
  "assets/js/screens/users.js",
  "assets/js/screens/nogas.js",
  "assets/js/screens/cities.js",
  "assets/js/screens/razgruzy.js",
  "assets/js/screens/trubki.js",
  "assets/js/screens/stats.js",
  "assets/js/screens/chat.js",
  "assets/js/screens/profile.js",
  "assets/js/screens/create-menu.js",
].forEach((file) => window.eval(fs.readFileSync(path.join(root, file), "utf8")));

const CHAT_PERMS = [
  "chat:read",
  "chat:write",
  "chat:direct",
  "users:manage",
  "users:read",
  "profile:rename",
  "dashboard:global",
  "operations:all",
  "operations:own",
  "cities:manage",
  "cities:read",
  "cities:all",
  "nogas:manage",
  "nogas:read",
  "nogas:all",
  "nogas:personal",
  "razgruz:manage",
  "razgruz:read",
  "razgruz:all",
];

const OWNER = {
  id: 1,
  telegram_id: 111,
  display_name: "Owner",
  role: "owner",
  role_label: "Owner",
  status: "active",
  created_at: "2026-01-01T10:00:00Z",
  features: { chat: true },
  permissions: CHAT_PERMS,
};

const NOGA_USER = {
  id: 9,
  telegram_id: 999,
  display_name: "Нога Тест",
  role: "noga",
  role_label: "Нога",
  status: "active",
  created_at: "2026-01-01T10:00:00Z",
  features: { chat: false },
  permissions: ["operations:own", "cities:read"],
};

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const assert = (condition, message) => {
  if (!condition) throw new Error("FAIL: " + message);
  console.log("ok:", message);
};
const $ = (id) => window.document.getElementById(id);

(async () => {
  window.NogaApi.setToken("test-token");
  window.NogaTelegram.notify = (message) => console.log("notify:", message);

  // --- SSE parser isolated ---
  const frames = [];
  const parser = window.NogaApi.createSseParser((frame) => frames.push(frame));
  parser.push("id: 1\neve");
  parser.push('nt: message.created\ndata: {"a":1');
  parser.push(',"b":2}\n\n');
  parser.push(": heartbeat\n\n");
  parser.push("id: 2\nevent: ping\ndata: line1\ndata: line2\n\n");
  assert(frames.length === 2, "parser собирает кадры через разрывы chunk");
  assert(frames[0].id === "1" && frames[0].event === "message.created", "первый кадр: id+event");
  assert(frames[0].data.a === 1 && frames[0].data.b === 2, "JSON data после склейки");
  assert(frames[1].data === "line1\nline2", "multiline data без JSON остаётся строкой");

  // --- Role without chat: no stream, bell hidden ---
  calls.length = 0;
  window.NogaRoles.setUser(NOGA_USER);
  window.NogaChat.syncAccess();
  await wait(20);
  assert($("bell").hidden === true, "без chat:read колокольчик скрыт");
  assert(
    !calls.some((c) => c.url.includes("/api/chat/stream")),
    "роль без права не запускает SSE"
  );
  window.NogaChat.show();
  assert($("viewChatRooms").hidden === true || $("viewHome"), "без права экран чата не открывается как рабочий вход");

  // --- Feature+permission gate and rooms ---
  calls.length = 0;
  window.NogaRoles.setUser(OWNER);
  window.NogaChat.syncAccess();
  await wait(40);
  assert($("bell").hidden === false, "с features.chat и chat:read колокольчик виден");
  assert(
    calls.some((c) => c.url.includes("/api/chat/rooms")),
    "после сессии подтягиваются комнаты"
  );
  assert(
    calls.some((c) => c.url.includes("/api/chat/stream")),
    "глобальный SSE стартует при доступе"
  );
  assert($("bellCount").hidden === false && $("bellCount").textContent === "2", "unread badge числовой");

  await window.NogaChat.show({ from: "home" });
  await wait(30);
  assert($("viewChatRooms").hidden === false, "открыт список комнат");
  const cards = $("chatRoomsList").querySelectorAll("[data-room-id]");
  assert(cards.length === 3, "системные и direct карточки в списке");
  assert(cards[0].getAttribute("data-room-id") === "1", "системная комната сверху");
  assert($("chatRoomsList").textContent.includes("Общий"), "название комнаты через textContent");
  assert(!$("chatRoomsList").innerHTML.includes("<script"), "нет сырого HTML из данных");

  await window.NogaChat.openRoom(2);
  await wait(10);
  assert($("viewChatRoom").hidden === false, "открыта пустая комната");
  assert($("chatRoomTitle").textContent === "Алерты", "заголовок комнаты");
  assert($("chatMessagesEmpty").hidden === false, "пустое состояние ленты");

  // --- Last-Event-ID on reconnect path ---
  const streamCall = calls.find((c) => c.url.includes("/api/chat/stream"));
  assert(streamCall.headers.Authorization === "Bearer test-token", "SSE шлёт Bearer");
  assert(
    streamCall.headers["Last-Event-ID"] === "10" || streamCall.headers["Last-Event-ID"] === 10,
    "SSE стартует с latest_event_id из rooms"
  );

  // --- Reconnect keeps Last-Event-ID from frames ---
  let reconnectHeaders = null;
  let connectCount = 0;
  window.NogaChat.release();
  window.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), method: options.method || "GET", headers: options.headers || {} });
    if (String(url).includes("/api/chat/stream")) {
      connectCount += 1;
      if (connectCount === 1) {
        return streamResponse([
          'id: 42\nevent: message.created\ndata: {"event_id":42,"type":"message.created","room_id":1,"data":{"message":{"id":99,"author":{"is_current_user":true},"preview":"я","created_at":"2026-08-01T13:00:00Z"}},"created_at":"2026-08-01T13:00:00Z"}\n\n',
        ]);
      }
      reconnectHeaders = options.headers || {};
      return streamResponse([]);
    }
    if (String(url).includes("/api/chat/rooms")) return response(roomsPayload);
    return response({});
  };
  window.NogaApi.setToken("test-token");
  const handle = window.NogaApi.openChatStream({
    lastEventId: 10,
    reconnectDelays: [5],
  });
  await wait(40);
  assert(connectCount >= 2, "после конца потока идёт reconnect");
  assert(
    String(reconnectHeaders["Last-Event-ID"]) === "42",
    "reconnect передаёт Last-Event-ID последнего кадра"
  );
  handle.abort();

  // --- Unauthorized cleanup ---
  let unauthorized = false;
  window.NogaApi.setUnauthorizedHandler(function () {
    unauthorized = true;
    window.NogaChat.release();
  });
  window.fetch = async (url) => {
    if (String(url).includes("/api/chat/stream")) {
      return response({ detail: { code: "UNAUTHORIZED", message: "no" } }, 401);
    }
    return response({});
  };
  const doomed = window.NogaApi.openChatStream({ lastEventId: 1, reconnectDelays: [1000] });
  await wait(30);
  assert(unauthorized === true, "401 на stream зовёт unauthorized handler");
  doomed.abort();
  window.NogaChat.release();
  assert(true, "release после unauthorized не падает");

  // --- Feature flag alone is not enough ---
  window.NogaRoles.setUser({
    ...OWNER,
    features: { chat: false },
  });
  window.NogaChat.syncAccess();
  await wait(10);
  assert($("bell").hidden === true, "features.chat=false скрывает чат даже при chat:read");

  console.log("\n_jsdom_chat.js: all checks passed");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
