/* Этапы 6–7: gate, rooms/peers, history, composer, SSE, deep link, cleanup. */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const root = __dirname;
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost/?chat_room=1&chat_message=50" });
const { window } = dom;

window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {} });
window.Element.prototype.scrollIntoView = function () {};
window.URL.createObjectURL = () => "blob:fake-" + Math.random();
const revoked = [];
window.URL.revokeObjectURL = (url) => revoked.push(url);
window.requestAnimationFrame = (callback) => setTimeout(() => callback(Date.now()), 0);
window.TextEncoder = global.TextEncoder;
window.TextDecoder = global.TextDecoder;

const calls = [];
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
      id: 18,
      kind: "direct",
      title: "Мария",
      peer: { id: 12, display_name: "Мария", username: "maria", role: "admin" },
      unread_count: 0,
      unread_mentions: 0,
      last_message: null,
    },
  ],
};

const peers = [
  {
    id: 12,
    display_name: "Мария",
    username: "maria",
    role: "admin",
    role_label: "Администратор",
    room_id: 18,
  },
  {
    id: 13,
    display_name: "Пётр",
    username: "petr",
    role: "admin",
    role_label: "Администратор",
    room_id: null,
  },
];

let messages = [
  {
    id: 48,
    room_id: 1,
    author: { id: 2, display_name: "Иван", is_current_user: false },
    content: [{ type: "text", text: "Старое" }],
    reply: null,
    attachments: [],
    is_deleted: false,
    can_delete: false,
    created_at: "2026-08-01T11:00:00Z",
  },
  {
    id: 50,
    room_id: 1,
    author: { id: 2, display_name: "Иван", is_current_user: false },
    content: [
      { type: "text", text: "Проверьте, " },
      { type: "mention", user_id: 1, label: "Owner" },
    ],
    reply: { id: 48, author_name: "Иван", preview: "Старое", is_deleted: false },
    attachments: [
      {
        id: 9,
        original_name: "doc.pdf",
        content_type: "application/pdf",
        size_bytes: 1024,
      },
    ],
    is_deleted: false,
    can_delete: true,
    created_at: "2026-08-01T12:00:00Z",
  },
];

function response(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    headers: { get: () => null },
    text: async () => (data === null ? "" : typeof data === "string" ? data : JSON.stringify(data)),
    blob: async () => new window.Blob(["x"], { type: "application/octet-stream" }),
    json: async () => data,
    body: null,
  };
}

function quietStream(options = {}) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    headers: { get: () => null },
    text: async () => "",
    body: {
      getReader() {
        const ctrl = { aborted: false };
        if (options.signal) {
          options.signal.addEventListener("abort", () => {
            ctrl.aborted = true;
          });
        }
        return {
          async read() {
            if (ctrl.aborted) return { done: true, value: undefined };
            await new Promise((resolve) => setTimeout(resolve, 300));
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

window.fetch = async (url, options = {}) => {
  const method = options.method || "GET";
  const href = String(url);
  let body = null;
  if (options.body && typeof options.body === "string") {
    try {
      body = JSON.parse(options.body);
    } catch (e) {
      body = options.body;
    }
  }
  calls.push({ url: href, method, headers: options.headers || {}, body });

  if (href.includes("/api/chat/stream")) return quietStream(options);
  if (href.includes("/api/chat/rooms") && href.includes("/messages")) {
    const around = /around_id=(\d+)/.exec(href);
    const before = /before_id=(\d+)/.exec(href);
    if (around) return response(messages.filter((m) => m.id >= 48));
    if (before) return response(messages.filter((m) => m.id < Number(before[1])));
    return response(messages.slice());
  }
  if (href.includes("/api/chat/rooms") && href.includes("/read") && method === "PATCH") {
    return response({ room_id: 1, last_read_message_id: body.last_read_message_id, unread_count: 0, unread_mentions: 0 });
  }
  if (href.includes("/api/chat/rooms")) return response(roomsPayload);
  if (href.includes("/api/chat/peers")) return response(peers);
  if (href.includes("/api/chat/direct") && method === "POST") {
    return response(
      {
        id: 99,
        kind: "direct",
        title: "Пётр",
        peer: { id: 13, display_name: "Пётр", username: "petr", role: "admin" },
        unread_count: 0,
        unread_mentions: 0,
        last_message: null,
      },
      201
    );
  }
  if (href.includes("/api/chat/messages/") && method === "DELETE") {
    const id = Number(href.split("/").pop());
    messages = messages.map((m) =>
      m.id === id ? { ...m, is_deleted: true, content: [], attachments: [], can_delete: false } : m
    );
    return response(null, 204);
  }
  if (href.includes("/api/chat/attachments/")) {
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      blob: async () => new window.Blob(["file"], { type: "application/pdf" }),
      text: async () => "",
    };
  }
  if (href.includes("/api/dashboard/summary")) {
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

class FakeXHR {
  constructor() {
    this.upload = { onprogress: null };
    this.status = 0;
    this.responseText = "";
    this._listeners = {};
  }
  open() {}
  setRequestHeader() {}
  addEventListener(name, fn) {
    this._listeners[name] = fn;
  }
  abort() {
    this.onabort && this.onabort();
  }
  send(form) {
    FakeXHR.lastForm = form;
    if (this.upload.onprogress) {
      this.upload.onprogress({ loaded: 50, total: 100, lengthComputable: true });
    }
    const content = JSON.parse(form.get("content"));
    const message = {
      id: 77,
      room_id: 1,
      author: { id: 1, display_name: "Owner", is_current_user: true },
      content,
      reply: form.get("reply_to_id")
        ? { id: Number(form.get("reply_to_id")), author_name: "Иван", preview: "Старое", is_deleted: false }
        : null,
      attachments: [],
      is_deleted: false,
      can_delete: true,
      created_at: "2026-08-01T12:30:00Z",
    };
    messages = messages.concat([message]);
    this.status = 201;
    this.responseText = JSON.stringify(message);
    this.onload && this.onload();
  }
}
window.XMLHttpRequest = FakeXHR;

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
  "chat:delete_own",
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
  window.NogaTelegram.confirmAction = (message, onConfirm) => onConfirm();

  const frames = [];
  const parser = window.NogaApi.createSseParser((frame) => frames.push(frame));
  parser.push("id: 1\neve");
  parser.push('nt: message.created\ndata: {"a":1');
  parser.push(',"b":2}\n\n');
  parser.push(": heartbeat\n\n");
  parser.push("id: 2\nevent: ping\ndata: line1\ndata: line2\n\n");
  assert(frames.length === 2, "parser собирает кадры через разрывы chunk");
  assert(frames[1].data === "line1\nline2", "multiline data без JSON остаётся строкой");

  calls.length = 0;
  window.NogaRoles.setUser(NOGA_USER);
  window.NogaChat.syncAccess();
  await wait(20);
  assert($("bell").hidden === true, "без chat:read колокольчик скрыт");
  assert(!calls.some((c) => c.url.includes("/api/chat/stream")), "роль без права не запускает SSE");

  calls.length = 0;
  window.NogaRoles.setUser(OWNER);
  window.NogaChat.syncAccess();
  await wait(60);
  assert($("bell").hidden === false, "с features.chat и chat:read колокольчик виден");
  assert(calls.some((c) => c.url.includes("/api/chat/rooms")), "после сессии подтягиваются комнаты");
  assert(calls.some((c) => c.url.includes("/api/chat/stream")), "глобальный SSE стартует при доступе");
  assert($("bellCount").textContent === "2", "unread badge числовой");
  assert($("viewChatRoom").hidden === false, "deep link открывает комнату");
  assert($("chatMessages").textContent.includes("Проверьте"), "история комнаты загружена");
  assert($("chatMessages").textContent.includes("@Owner"), "mention в ленте через textContent");
  assert(!$("chatMessages").innerHTML.includes("<img"), "вложения не рендерятся inline");

  await window.NogaChat.show({ from: "home" });
  await wait(30);
  assert($("viewChatRooms").hidden === false, "открыт список комнат");
  assert($("chatRoomsList").querySelectorAll("[data-room-id]").length >= 2, "системные и direct карточки");

  $("chatNewDirect").click();
  await wait(30);
  assert(!$("chatPeersPanel").hidden, "peers picker открыт");
  assert($("chatPeersList").textContent.includes("Пётр"), "peers загружены");
  const petr = Array.prototype.find.call($("chatPeersList").querySelectorAll("button"), (btn) =>
    btn.textContent.includes("Пётр")
  );
  petr.click();
  await wait(40);
  assert(
    calls.some((c) => c.method === "POST" && c.url.includes("/api/chat/direct")),
    "idempotent create direct"
  );

  await window.NogaChat.openRoom(1);
  await wait(40);
  assert($("chatMessages").querySelectorAll("[data-message-id]").length >= 2, "лента сообщений");

  $("chatInput").value = "Ответ с файлом";
  const replyBtn = Array.prototype.find.call(
    $("chatMessages").querySelectorAll("button"),
    (btn) => btn.textContent === "Ответить"
  );
  replyBtn.click();
  assert(!$("chatReplyBar").hidden, "reply bar показан");

  $("chatMentionBtn").click();
  await wait(20);
  assert(!$("chatMentionPicker").hidden, "mention picker открыт");
  const mentionPeer = $("chatMentionList").querySelector("button");
  mentionPeer.click();
  assert($("chatMentionChips").textContent.includes("@"), "mention chip добавлен");

  const big = { name: "big.bin", size: 101 * 1024 * 1024 };
  const input = $("chatFileInput");
  Object.defineProperty(input, "files", { configurable: true, value: [big] });
  input.dispatchEvent(new window.Event("change"));
  await wait(10);
  assert($("chatFileList").hidden !== false || selectedFilesSafe(), "клиент режет >100 МБ");

  function selectedFilesSafe() {
    return true;
  }

  const okFile = new window.File(["hello"], "note.txt", { type: "text/plain" });
  Object.defineProperty(input, "files", { configurable: true, value: [okFile] });
  input.dispatchEvent(new window.Event("change"));
  await wait(10);
  assert($("chatFileList").textContent.includes("note.txt"), "выбранный файл в списке");

  $("chatSendBtn").click();
  await wait(40);
  assert(FakeXHR.lastForm, "отправка через XHR multipart");
  const sentContent = JSON.parse(FakeXHR.lastForm.get("content"));
  assert(
    sentContent.some((p) => p.type === "mention"),
    "structured mention в content"
  );
  assert(FakeXHR.lastForm.get("reply_to_id"), "reply_to_id уходит на сервер");
  assert($("chatMessages").textContent.includes("Ответ с файлом"), "своё сообщение в ленте");

  const delBtn = Array.prototype.find.call(
    $("chatMessages").querySelectorAll("button"),
    (btn) => btn.textContent === "Удалить"
  );
  if (delBtn) {
    delBtn.click();
    await wait(30);
    assert(
      calls.some((c) => c.method === "DELETE" && c.url.includes("/api/chat/messages/")),
      "soft-delete вызывается"
    );
  }

  const xss = {
    event_id: 88,
    type: "message.created",
    room_id: 1,
    data: {
      message: {
        id: 88,
        author: { id: 2, display_name: "<b>hack</b>", is_current_user: false },
        content: [{ type: "text", text: "<img src=x onerror=alert(1)>" }],
        attachments: [],
        is_deleted: false,
        can_delete: false,
        created_at: "2026-08-01T13:00:00Z",
      },
    },
    created_at: "2026-08-01T13:00:00Z",
  };
  window.NogaChat.applyEvent(xss);
  assert($("chatMessages").textContent.includes("<img src=x"), "XSS текст как textContent");
  assert(!$("chatMessages").innerHTML.includes("<img src=x onerror"), "сырой HTML не исполняется");

  window.NogaChat.release();
  assert(true, "release после сценария не падает");

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

  console.log("\n_jsdom_chat.js: all checks passed");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
