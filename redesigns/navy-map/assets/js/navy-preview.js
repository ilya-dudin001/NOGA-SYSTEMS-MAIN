(function (global) {
  "use strict";

  var params = new URLSearchParams(global.location.search);
  if (params.get("preview") !== "1") return;

  var now = "2026-07-28T18:40:00Z";
  var user = {
    id: 1,
    telegram_id: 100000001,
    username: "alexey",
    display_name: "Алексей",
    role: "owner",
    role_label: "Owner",
    status: "active",
    created_at: "2026-01-14T10:00:00Z",
    last_seen_at: now,
    permissions: [
      "users:read", "users:manage", "users:delete", "profile:rename",
      "dashboard:global", "operations:all", "operations:own", "operations:confirm",
      "operations:payout", "settings:manage", "cities:read", "cities:manage",
      "cities:all", "nogas:read", "nogas:manage", "nogas:all", "nogas:personal",
      "razgruz:read", "razgruz:manage", "razgruz:all"
    ],
  };

  var razgruzy = [
    { id: 1, name: "Альфа", commission_percent: 3.5, contact: "@alpha", is_active: true, completed_orders: 18, cities_count: 4, created_by_name: "Алексей", created_by_me: true, can_manage: true, created_at: "2026-05-11T09:00:00Z" },
    { id: 2, name: "Вектор", commission_percent: 4, contact: "+7 900 555-11-22", is_active: true, completed_orders: 9, cities_count: 3, created_by_name: "Мария", created_by_me: false, can_manage: true, created_at: "2026-05-19T12:00:00Z" },
    { id: 3, name: "Север", commission_percent: 2.8, contact: "@north", is_active: false, completed_orders: 6, cities_count: 1, created_by_name: "Алексей", created_by_me: true, can_manage: true, created_at: "2026-06-02T08:30:00Z" },
  ];

  var nogas = [
    { id: 1, name: "Андрей", city_id: 1, city_name: "Москва", initial_city_name: "Москва", last_city_name: "Москва", is_test: false, is_active: true, can_manage: true, has_personal_access: true, created_by_name: "Илья", created_at: "2026-05-04T10:00:00Z", address: "Москва, ул. Тверская, 12", phones: ["+7 900 111-22-33"], telegrams: ["@andrey"], files: [] },
    { id: 2, name: "Максим", city_id: 2, city_name: "Самара", initial_city_name: "Казань", last_city_name: "Самара", is_test: false, is_active: true, can_manage: true, has_personal_access: true, created_by_name: "Олег", created_at: "2026-05-12T11:00:00Z", address: "Самара, Московское шоссе, 8", phones: ["+7 900 222-33-44"], telegrams: ["@maxim"], files: [] },
    { id: 3, name: "Роман", city_id: 3, city_name: "Воронеж", initial_city_name: "Воронеж", last_city_name: "Воронеж", is_test: true, is_active: true, can_manage: true, has_personal_access: true, created_by_name: "Анна", created_at: "2026-06-01T13:00:00Z", address: "Воронеж, ул. Кольцовская, 31", phones: ["+7 900 333-44-55"], telegrams: ["@roman"], files: [] },
    { id: 4, name: "Сергей", city_id: null, city_name: null, initial_city_name: "Тула", last_city_name: "Тула", is_test: false, is_active: false, can_manage: true, has_personal_access: true, created_by_name: "Алексей", created_at: "2026-06-14T15:00:00Z", address: "", phones: [], telegrams: [], files: [] },
  ];

  var cities = [
    { id: 1, name: "Москва", status: "working", min_amount: 500000, min_amount_currency: "RUB", nogas_count: 1, razgruzy: [razgruzy[0], razgruzy[1]], can_manage: true, created_by_name: "Алексей" },
    { id: 2, name: "Самара", status: "working", min_amount: 250000, min_amount_currency: "RUB", nogas_count: 1, razgruzy: [razgruzy[0]], can_manage: true, created_by_name: "Олег" },
    { id: 3, name: "Воронеж", status: "working", min_amount: 180000, min_amount_currency: "RUB", nogas_count: 1, razgruzy: [razgruzy[1]], can_manage: true, created_by_name: "Анна" },
    { id: 4, name: "Тула", status: "working", min_amount: 200000, min_amount_currency: "RUB", nogas_count: 0, razgruzy: [razgruzy[0]], can_manage: true, created_by_name: "Алексей" },
    { id: 5, name: "Казань", status: "working", min_amount: 300000, min_amount_currency: "RUB", nogas_count: 2, razgruzy: [], can_manage: true, created_by_name: "Мария" },
    { id: 6, name: "Омск", status: "paused", min_amount: 220000, min_amount_currency: "RUB", nogas_count: 1, razgruzy: [razgruzy[2]], can_manage: true, created_by_name: "Алексей" },
  ];

  var trubki = [
    { id: 1042, status: "vedut", city_id: 1, city_name: "Москва", noga_id: 1, noga_name: "Андрей", noga_owner_name: "Илья", razgruz_id: 1, razgruz_name: "Альфа", amount: 450000, amount_currency: "RUB", customer_name: "Иван Петров", customer_address: "Москва, ул. Арбат, 18", delivery: "zahod", created_by_name: "Алексей", created_at: "2026-07-28T18:28:00Z", can_manage: true },
    { id: 1041, status: "zacep", city_id: 2, city_name: "Самара", noga_id: 2, noga_name: "Максим", noga_owner_name: "Олег", razgruz_id: null, razgruz_name: null, amount: 2800, amount_currency: "USD", customer_name: "Павел Орлов", customer_address: "Самара, ул. Молодогвардейская, 92", delivery: "taxi", created_by_name: "Мария", created_at: "2026-07-28T18:06:00Z", can_manage: true },
    { id: 1039, status: "zabrali", city_id: 3, city_name: "Воронеж", noga_id: 3, noga_name: "Роман", noga_owner_name: "Анна", razgruz_id: 2, razgruz_name: "Вектор", amount: 180000, amount_currency: "RUB", customer_name: "Олег Серов", customer_address: "Воронеж, Московский проспект, 44", delivery: "zahod", created_by_name: "Алексей", created_at: "2026-07-28T17:01:00Z", can_manage: true },
    { id: 1038, status: "razgruzheno", city_id: 1, city_name: "Москва", noga_id: 1, noga_name: "Андрей", noga_owner_name: "Илья", razgruz_id: 1, razgruz_name: "Альфа", amount: 620000, amount_currency: "RUB", customer_name: "Антон К.", customer_address: "Москва, Ленинский проспект, 77", delivery: "taxi", created_by_name: "Мария", created_at: "2026-07-28T15:32:00Z", can_manage: true },
    { id: 1037, status: "srez", city_id: 2, city_name: "Самара", noga_id: 2, noga_name: "Максим", noga_owner_name: "Олег", razgruz_id: null, razgruz_name: null, amount: 90000, amount_currency: "RUB", customer_name: "Михаил Р.", customer_address: "Самара, ул. Ново-Садовая, 21", delivery: "zahod", created_by_name: "Алексей", created_at: "2026-07-28T14:10:00Z", can_manage: true },
  ];

  var users = [
    user,
    { id: 2, telegram_id: 100000002, username: "maria", display_name: "Мария", role: "right_hand", status: "active" },
    { id: 3, telegram_id: 100000003, username: "oleg", display_name: "Олег", role: "admin", status: "active" },
    { id: 4, telegram_id: 100000004, username: "ivan", display_name: "Иван", role: "noga", status: "blocked" },
  ];

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function nextId(items) {
    return items.reduce(function (max, item) { return Math.max(max, item.id); }, 0) + 1;
  }

  function update(items, id, patch) {
    var item = items.filter(function (entry) { return entry.id === Number(id); })[0];
    if (item) Object.keys(patch || {}).forEach(function (key) { item[key] = patch[key]; });
    return clone(item || {});
  }

  function remove(items, id) {
    var index = -1;
    for (var i = 0; i < items.length; i += 1) {
      if (items[i].id === Number(id)) {
        index = i;
        break;
      }
    }
    if (index !== -1) items.splice(index, 1);
    return { ok: true };
  }

  function cityDetail(id) {
    var city = clone(cities.filter(function (item) { return item.id === Number(id); })[0]);
    city.nogas = clone(nogas.filter(function (noga) { return noga.city_id === city.id; }));
    city.recent_orders = clone(trubki.filter(function (item) { return item.city_id === city.id; }).slice(0, 3));
    return city;
  }

  function summary() {
    function count(items, field, value) {
      return items.filter(function (item) { return item[field] === value; }).length;
    }
    return {
      scope: "global",
      turnover_rub: 0,
      turnover_usd: 0,
      cities: {
        total: cities.length,
        working: count(cities, "status", "working"),
        paused: count(cities, "status", "paused"),
        stopped: count(cities, "status", "stopped"),
        nogas: nogas.length,
        razgruzy: razgruzy.length,
      },
      trubki: {
        total: trubki.length,
        zacep: count(trubki, "status", "zacep"),
        vedut: count(trubki, "status", "vedut"),
        srez: count(trubki, "status", "srez"),
        zabrali: count(trubki, "status", "zabrali"),
        razgruzheno: count(trubki, "status", "razgruzheno"),
      },
    };
  }

  global.NogaTelegram.getInitData = function () { return "navy-preview"; };
  global.NogaTelegram.isTelegramContext = function () { return true; };
  global.NogaApi.authTelegram = async function () {
    return { access_token: "preview-token", user: clone(user) };
  };
  global.NogaApi.dashboardSummary = async function () { return summary(); };
  global.NogaApi.listTrubki = async function (options) {
    var result = trubki.slice();
    if (options && options.status) result = result.filter(function (item) { return item.status === options.status; });
    if (options && options.limit) result = result.slice(0, options.limit);
    return clone(result);
  };
  global.NogaApi.getTrubka = async function (id) { return clone(trubki.filter(function (item) { return item.id === Number(id); })[0]); };
  global.NogaApi.listCities = async function (scope) {
    var result = scope === "working" ? cities.filter(function (city) { return city.status === "working"; }) : cities;
    return clone(result);
  };
  global.NogaApi.getCity = async function (id) { return cityDetail(id); };
  global.NogaApi.listNogas = async function () { return clone(nogas); };
  global.NogaApi.getNoga = async function (id) { return clone(nogas.filter(function (item) { return item.id === Number(id); })[0]); };
  global.NogaApi.listRazgruzy = async function () { return clone(razgruzy); };
  global.NogaApi.listUsers = async function () { return clone(users); };

  global.NogaApi.updateMe = async function (patch) {
    Object.keys(patch).forEach(function (key) { user[key] = patch[key]; });
    return clone(user);
  };
  global.NogaApi.createTrubka = async function (payload) {
    var item = Object.assign({ id: nextId(trubki), created_at: now, created_by_name: user.display_name, can_manage: true }, payload);
    trubki.unshift(item);
    return clone(item);
  };
  global.NogaApi.updateTrubka = async function (id, payload) { return update(trubki, id, payload); };
  global.NogaApi.deleteTrubka = async function (id) { return remove(trubki, id); };
  global.NogaApi.createCity = async function (payload) {
    var item = Object.assign({ id: nextId(cities), nogas_count: 0, razgruzy: [], can_manage: true, created_by_name: user.display_name }, payload);
    cities.push(item);
    return clone(item);
  };
  global.NogaApi.updateCity = async function (id, payload) { return update(cities, id, payload); };
  global.NogaApi.deleteCity = async function (id) { return remove(cities, id); };
  global.NogaApi.createNoga = async function (payload) {
    var item = Object.assign({ id: nextId(nogas), created_at: now, created_by_name: user.display_name, can_manage: true, has_personal_access: true, is_active: true, address: "", phones: [], telegrams: [], files: [] }, payload);
    nogas.push(item);
    return clone(item);
  };
  global.NogaApi.updateNoga = async function (id, payload) { return update(nogas, id, payload); };
  global.NogaApi.deleteNoga = async function (id) { return remove(nogas, id); };
  global.NogaApi.createRazgruz = async function (payload) {
    var item = Object.assign({ id: nextId(razgruzy), completed_orders: 0, cities_count: 0, created_at: now, created_by_name: user.display_name, created_by_me: true, can_manage: true, is_active: true }, payload);
    razgruzy.push(item);
    return clone(item);
  };
  global.NogaApi.updateRazgruz = async function (id, payload) { return update(razgruzy, id, payload); };
  global.NogaApi.deleteRazgruz = async function (id) { return remove(razgruzy, id); };
  global.NogaApi.createUser = async function (payload) {
    var item = Object.assign({ id: nextId(users), status: "active" }, payload);
    users.push(item);
    return clone(item);
  };
  global.NogaApi.updateUser = async function (id, payload) { return update(users, id, payload); };
  global.NogaApi.deleteUser = async function (id) { return remove(users, id); };
})(window);
