/* Временный smoke-тест фронта в jsdom: трубки, детали, форма и меню «+». */
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
window.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
window.performance = window.performance || { now: () => Date.now() };

const TRUBKI = [
  {
    id: 1,
    status: "vedut",
    city_id: 1,
    city_name: "Тула",
    amount: 250000,
    amount_currency: "RUB",
    noga_id: 7,
    noga_name: "Пётр",
    noga_owner_name: "Админ",
    razgruz_id: 3,
    razgruz_name: "Альфа",
    customer_name: "Иванов Иван Иванович",
    customer_address: "Тула, Ленина 1",
    delivery: "taxi",
    created_at: "2026-07-28T10:00:00Z",
    updated_at: "2026-07-28T10:00:00Z",
    created_by_name: "Owner",
    can_manage: true,
  },
  {
    id: 2,
    status: "razgruzheno",
    city_id: 1,
    city_name: "Самара",
    amount: 1200000,
    amount_currency: "RUB",
    noga_id: 8,
    noga_name: "Анна",
    noga_owner_name: "Owner",
    razgruz_id: null,
    razgruz_name: null,
    customer_name: "Петров П. П.",
    customer_address: "Самара, Мира 4",
    delivery: "zahod",
    created_at: "2026-07-27T10:00:00Z",
    updated_at: "2026-07-27T10:00:00Z",
    created_by_name: "Owner",
    can_manage: true,
  },
];

const CITY_DETAIL = {
  id: 1,
  name: "Тула",
  status: "working",
  min_amount: null,
  min_amount_currency: null,
  nogas_count: 2,
  razgruzy: [
    { id: 3, name: "Альфа", commission_percent: 3.5, is_active: true, created_at: "2026-07-01T10:00:00Z", cities_count: 1, completed_orders: 0, can_manage: true, created_by_me: true },
  ],
  nogas: [
    { id: 7, name: "Пётр", is_test: false, is_active: true, created_at: "2026-07-01T10:00:00Z", created_by_name: "Админ", can_manage: true },
    { id: 8, name: "Анна", is_test: false, is_active: true, created_at: "2026-07-01T10:00:00Z", created_by_name: "Owner", can_manage: true },
  ],
  recent_orders: [],
  created_at: "2026-07-01T10:00:00Z",
  created_by_name: "Owner",
  can_manage: true,
};

const NOGA_DETAIL = {
  id: 7,
  name: "Пётр",
  city_id: 1,
  city_name: "Тула",
  initial_city_name: "Тула",
  last_city_name: "Тула",
  is_test: false,
  is_active: true,
  created_at: "2026-07-01T10:00:00Z",
  created_by_name: "Админ",
  can_manage: true,
  address: "Тула, Гагарина 3",
  phones: ["+7 900 000-00-00"],
  telegrams: ["@petr"],
  files: [],
  has_personal_access: true,
};

const calls = [];

window.fetch = async (url, options) => {
  options = options || {};
  const method = options.method || "GET";
  calls.push({ url, method, body: options.body ? JSON.parse(options.body) : null });

  let data = null;
  if (url.indexOf("/api/trubki/") !== -1) data = TRUBKI[0];
  else if (url.indexOf("/api/trubki") !== -1) data = method === "POST" ? TRUBKI[0] : TRUBKI;
  else if (url.indexOf("/api/cities/1") !== -1) data = CITY_DETAIL;
  else if (url.indexOf("/api/cities") !== -1) data = [CITY_DETAIL];
  else if (url.indexOf("/api/nogas/") !== -1) data = NOGA_DETAIL;
  else if (url.indexOf("/api/dashboard/summary") !== -1) {
    data = {
      turnover_rub: 0,
      turnover_usd: 0,
      scope: "global",
      cities: { total: 1, working: 1, paused: 0, stopped: 0, nogas: 2, razgruzy: 1 },
      trubki: { total: 2, zacep: 0, vedut: 1, srez: 0, zabrali: 0, razgruzheno: 1 },
    };
  } else data = {};

  return {
    ok: true,
    status: 200,
    statusText: "OK",
    text: async () => JSON.stringify(data),
  };
};

const files = [
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
  "assets/js/screens/profile.js",
  "assets/js/screens/create-menu.js",
];
files.forEach((file) => {
  window.eval(fs.readFileSync(path.join(root, file), "utf8"));
});

const OWNER = {
  id: 1,
  telegram_id: 111,
  display_name: "Owner",
  role: "owner",
  role_label: "Owner",
  status: "active",
  created_at: "2026-01-01T10:00:00Z",
  permissions: [
    "users:manage", "users:read", "users:delete", "profile:rename", "dashboard:global",
    "operations:all", "operations:own", "cities:manage", "cities:read", "cities:all",
    "nogas:manage", "nogas:read", "nogas:all", "nogas:personal",
    "razgruz:manage", "razgruz:read", "razgruz:all",
  ],
};

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const assert = (cond, msg) => {
  if (!cond) throw new Error("FAIL: " + msg);
  console.log("ok:", msg);
};
const $ = (id) => window.document.getElementById(id);

(async () => {
  window.NogaRoles.setUser(OWNER);
  window.NogaCreateMenu.bind();
  window.NogaDashboard.applyUser(OWNER);
  window.NogaTelegram.notify = (m) => console.log("   notify:", m);

  // --- дашборд ---
  window.NogaDashboard.applySummary(await (await window.fetch("/api/dashboard/summary")).text ? JSON.parse(await (await window.fetch("/api/dashboard/summary")).text()) : {});
  await wait(60);

  assert($("trubkiTotal").textContent === "2", "счётчик трубок на дашборде = 2");
  const rows = $("dashTrubki").querySelectorAll(".trubki-table__row");
  assert(rows.length === 2, "в таблице дашборда 2 строки");
  const cells = rows[0].querySelectorAll("td");
  assert(cells.length === 5, "в строке 5 колонок");
  assert(cells[0].textContent === "Ведут", "первая колонка — статус «Ведут»");
  assert(cells[1].textContent === "Тула", "вторая колонка — город");
  assert(cells[2].textContent.indexOf("250к") === 0, "третья колонка — сумма 250к: " + cells[2].textContent);
  assert(cells[3].textContent === "Пётр", "четвёртая колонка — нога");
  assert(cells[4].textContent === "Админ", "пятая колонка — чья нога");
  assert(
    rows[1].querySelector(".trubka-status--razgruzheno") !== null,
    "золотой статус «Разгружено» получил свой класс"
  );

  // --- детали по клику ---
  rows[0].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await wait(80);
  assert($("viewTrubka").hidden === false, "открылась страница деталей");
  const body = $("trubkaBody").textContent;
  assert(body.indexOf("Иванов Иван Иванович") !== -1, "в деталях есть ФИО заказчика");
  assert(body.indexOf("Тула, Ленина 1") !== -1, "в деталях есть адрес заказчика");
  assert(body.indexOf("Такси") !== -1, "в деталях указан способ передачи");
  const frame = $("trubkaBody").querySelector(".map-block__frame");
  assert(frame && frame.src.indexOf("output=embed") !== -1, "есть карта с адресом");
  assert(
    decodeURIComponent(frame.src).indexOf("Тула, Ленина 1") !== -1,
    "в карту передан адрес заказчика"
  );
  await wait(200);
  const panel = $("trubkaBody").querySelector(".detail-list__panel");
  console.log("   panel:", panel && panel.textContent.slice(0, 200));
  assert(
    $("trubkaBody").querySelector("textarea") &&
      $("trubkaBody").querySelector("textarea").value.indexOf("Гагарина 3") !== -1,
    "подтянулись подробности ноги"
  );
  assert($("btnEditTrubka").hidden === false, "кнопка правки доступна"); 

  // --- правка из деталей ---
  $("btnEditTrubka").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await wait(120);
  assert($("viewTrubki").hidden === false, "перешли на экран трубок");
  assert($("trubkaForm").hidden === false, "форма открылась");
  assert($("trubkaCustomer").value === "Иванов Иван Иванович", "форма заполнена заказчиком");
  assert($("trubkaStatusField").value === "vedut", "в форме выбран текущий статус");
  assert($("trubkaCity").value === "1", "в форме выбран город");
  assert($("trubkaNoga").value === "7", "в форме выбрана нога из состава города");
  assert($("trubkaRazgruz").value === "3", "в форме выбран разгруз города");

  $("trubkaStatusField").value = "zabrali";
  $("trubkaAmount").value = "300000";
  window.document
    .querySelector('#trubkaDeliverySwitch .segmented__btn[data-value="zahod"]')
    .dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  $("trubkaForm").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await wait(120);

  const patch = calls.filter((c) => c.method === "PATCH").pop();
  assert(patch && patch.url.indexOf("/api/trubki/1") !== -1, "ушёл PATCH по трубке");
  assert(patch.body.status === "zabrali", "статус в теле запроса изменён");
  assert(patch.body.amount === 300000, "сумма в теле запроса изменена");
  assert(patch.body.delivery === "zahod", "способ передачи в теле запроса изменён");
  assert($("viewTrubka").hidden === false, "после сохранения вернулись в детали");

  // --- фильтры на экране списка ---
  await window.NogaTrubki.show({ status: "" });
  await wait(60);
  const filters = $("trubkiFilters").querySelectorAll(".tabs__btn");
  assert(filters.length === 6, "фильтров шесть: «Все» и пять стадий");
  filters[3].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await wait(60);
  const lastList = calls.filter((c) => c.method === "GET" && c.url.indexOf("/api/trubki?") !== -1).pop();
  assert(lastList.url.indexOf("status=srez") !== -1, "фильтр ушёл в запрос: " + lastList.url);

  // --- меню на «+» ---
  $("fab").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await wait(60);
  assert($("fabMenu").hidden === false, "меню создания открылось");
  assert($("fabMenu").classList.contains("is-open"), "меню получило класс анимации");
  const menuItems = $("fabMenuList").querySelectorAll(".fab-menu__item");
  assert(menuItems.length === 4, "в меню четыре пункта");
  assert(
    Array.prototype.map.call(menuItems, (b) => b.textContent).join("/") ===
      "Трубка/Город/Нога/Разгруз",
    "порядок пунктов меню"
  );

  menuItems[0].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await wait(300);
  assert($("fabMenu").hidden === true, "меню закрылось после выбора");
  assert($("viewTrubki").hidden === false && $("trubkaForm").hidden === false,
    "открылась форма новой трубки");
  assert($("trubkaFormTitle").textContent === "Новая трубка", "заголовок формы для создания");

  // --- создание ---
  $("trubkaCity").value = "1";
  $("trubkaCity").dispatchEvent(new window.Event("change", { bubbles: true }));
  await wait(80);
  $("trubkaNoga").value = "8";
  $("trubkaAmount").value = "500000";
  $("trubkaCustomer").value = "Сидоров С. С.";
  $("trubkaAddress").value = "Тула, Мира 12";
  $("trubkaForm").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await wait(150);

  const post = calls.filter((c) => c.method === "POST").pop();
  assert(post && post.url.indexOf("/api/trubki") !== -1, "ушёл POST новой трубки");
  assert(post.body.noga_id === 8 && post.body.city_id === 1, "город и нога в теле запроса");
  assert(post.body.customer_name === "Сидоров С. С.", "ФИО в теле запроса");
  assert(post.body.customer_address === "Тула, Мира 12", "адрес в теле запроса");
  assert(post.body.delivery === "zahod", "способ передачи по умолчанию — заход");

  // --- роль noga меню не получает ---
  window.NogaRoles.setUser({ ...OWNER, role: "noga", permissions: ["operations:own", "cities:read"] });
  $("fab").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await wait(60);
  assert($("fabMenu").hidden === true, "у роли «нога» меню не открывается");

  console.log("\nALL JSDOM TRUBKI CHECKS PASSED");
})().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
