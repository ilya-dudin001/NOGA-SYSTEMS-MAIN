/* Smoke-тест многошагового создания и карточки трубки в jsdom. */
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

const CITY = {
  id: 1,
  name: "Тула",
  status: "working",
  nogas: [{ id: 7, name: "Иван", created_by_name: "Админ" }],
  razgruzy: [],
};

let trubka = {
  id: 125,
  status: "zacep",
  city_id: 1,
  city_name: "Тула",
  amount: 500000,
  amount_currency: "RUB",
  noga_id: 7,
  noga_name: "Иван",
  noga_owner_name: "Админ",
  razgruz_id: null,
  razgruz_name: null,
  customer_name: null,
  customer_address: null,
  delivery: null,
  recalculation_amount: null,
  noga_payout: null,
  remainder: null,
  usdt_received: null,
  report_sent_at: null,
  files: [],
  history: [
    {
      id: 1,
      action: "created",
      actor_name: "Owner",
      payload: {},
      created_at: "2026-08-01T10:24:00Z",
    },
  ],
  created_at: "2026-08-01T10:24:00Z",
  updated_at: "2026-08-01T10:24:00Z",
  created_by_name: "Owner",
  can_manage: true,
};

const calls = [];
function response(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    text: async () => (data === null ? "" : JSON.stringify(data)),
    blob: async () => new window.Blob(["image"], { type: "image/png" }),
  };
}

window.fetch = async (url, options = {}) => {
  const method = options.method || "GET";
  let body = null;
  if (options.body && typeof options.body === "string") body = JSON.parse(options.body);
  calls.push({ url, method, body });

  if (url.includes("/api/dashboard/summary")) {
    return response({
      turnover_rub: 0,
      turnover_usd: 0,
      scope: "global",
      cities: { total: 1, working: 1, paused: 0, stopped: 0, nogas: 1, razgruzy: 0 },
      trubki: { total: 1, zacep: 1, zabrali: 0, razgruzhaetsya: 0, vyplacheno: 0, srez: 0 },
    });
  }
  if (url.includes("/api/cities/1")) return response(CITY);
  if (url.includes("/api/cities")) return response([CITY]);
  if (url.includes("/files/") && method === "GET") return response(new window.Blob(["image"]));
  if (url.endsWith("/recalculation") && method === "POST") {
    trubka = {
      ...trubka,
      status: "razgruzhaetsya",
      recalculation_amount: body.amount,
      noga_payout: Math.round(body.amount * 0.1),
      remainder: body.amount - Math.round(body.amount * 0.1),
    };
    return response(trubka);
  }
  if (url.endsWith("/usdt") && method === "POST") {
    trubka = { ...trubka, status: "vyplacheno", usdt_received: body.amount };
    return response(trubka);
  }
  if (url.endsWith("/report") && method === "POST") {
    trubka = { ...trubka, report_sent_at: "2026-08-01T11:00:00Z" };
    return response(trubka);
  }
  if (url.includes("/files") && method === "POST") {
    const kind = options.body.get("kind");
    trubka = {
      ...trubka,
      files: trubka.files.concat({
        id: trubka.files.length + 1,
        kind,
        original_name: "photo.jpg",
        content_type: "image/jpeg",
        size_bytes: 100,
        created_at: "2026-08-01T10:30:00Z",
      }),
    };
    return response(trubka.files[trubka.files.length - 1], 201);
  }
  if (/\/api\/trubki\/125$/.test(url)) {
    if (method === "PATCH") trubka = { ...trubka, ...body };
    return response(trubka);
  }
  if (url.includes("/api/trubki")) {
    if (method === "POST") return response(trubka, 201);
    return response([trubka]);
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
  "assets/js/screens/trubki.js",
  "assets/js/screens/stats.js",
  "assets/js/screens/profile.js",
  "assets/js/screens/create-menu.js",
].forEach((file) => window.eval(fs.readFileSync(path.join(root, file), "utf8")));

const OWNER = {
  id: 1,
  telegram_id: 111,
  display_name: "Owner",
  role: "owner",
  role_label: "Owner",
  status: "active",
  created_at: "2026-01-01T10:00:00Z",
  permissions: [
    "users:manage",
    "users:read",
    "users:delete",
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
  ],
};

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const assert = (condition, message) => {
  if (!condition) throw new Error("FAIL: " + message);
  console.log("ok:", message);
};
const $ = (id) => window.document.getElementById(id);

(async () => {
  window.NogaRoles.setUser(OWNER);
  window.NogaTelegram.notify = (message) => console.log("notify:", message);

  await window.NogaTrubki.openCreate();
  assert($("viewTrubkaCreate").hidden === false, "открыт экран создания трубки");
  assert(!$("trubkaStatusField"), "на первом шаге нет выбора статуса");
  assert(!$("trubkaStepOne").hidden && $("trubkaStepTwo").hidden, "открыт первый шаг");
  assert($("trubkaCity"), "на первом шаге есть выбор города");

  $("trubkaCity").value = "1";
  $("btnTrubkaNext").click();
  await wait(20);
  assert($("trubkaStepOne").hidden && !$("trubkaStepTwo").hidden, "открыт второй шаг");
  assert($("trubkaNoga").options.length === 2, "загружены ноги выбранного города");

  $("trubkaNoga").value = "7";
  $("trubkaAmount").value = "500000";
  $("trubkaForm").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await wait(30);
  const createCall = calls.find((call) => call.method === "POST" && /\/api\/trubki$/.test(call.url));
  assert(createCall && createCall.body.status === "zacep", "создание отправляет статус «Зацеп»");
  assert($("viewTrubka").hidden === false, "после создания открыты детали");
  assert($("trubkaBody").textContent.includes("EM-000125"), "показан номер трубки");
  assert($("trubkaBody").textContent.includes("Данные клиента"), "есть скрываемый блок клиента");

  const recalculation = $("trubkaBody").querySelector(".em-trubka-money-input");
  recalculation.value = "500000";
  recalculation.dispatchEvent(new window.Event("input", { bubbles: true }));
  const values = $("trubkaBody").querySelectorAll(".em-money__value");
  assert(values[0].textContent.includes("50"), "выплата ноге рассчитана моментально");
  assert(values[1].textContent.includes("450"), "остаток рассчитан моментально");
  assert($("trubkaStageAction").disabled, "без фото пересчёт недоступен");

  const moneyInput = $("trubkaBody").querySelector('input[type="file"]');
  Object.defineProperty(moneyInput, "files", {
    value: [new window.File(["photo"], "money.jpg", { type: "image/jpeg" })],
  });
  moneyInput.dispatchEvent(new window.Event("change", { bubbles: true }));
  await wait(30);
  assert(!$("trubkaStageAction").disabled, "после фото и суммы пересчёт доступен");
  $("trubkaStageAction").click();
  await wait(30);
  assert($("trubkaBody").textContent.includes("Зашло на счёт, USDT"), "открыт этап отчёта");
  assert(trubka.status === "razgruzhaetsya", "статус автоматически стал «Разгружается»");

  const statusLabels = window.NogaDict.TRUBKA_MANUAL_STATUSES.map((item) => item.label);
  assert(
    statusLabels.join("/") === "Зацеп/Забрали/Выплачено/Срез",
    "ручные статусы соответствуют требованиям"
  );

  console.log("\nALL JSDOM TRUBKI CHECKS PASSED");
})().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
