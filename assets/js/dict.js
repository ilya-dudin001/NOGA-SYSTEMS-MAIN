/* Справочники, общие для экранов: статусы городов и валюты порогов. */
(function (global) {
  "use strict";

  var CITY_STATUSES = [
    { value: "working", label: "В работе", short: "В работе", cls: "status-pill--working" },
    {
      value: "paused",
      label: "На стопе (временно)",
      short: "Стоп врем.",
      cls: "status-pill--paused",
    },
    {
      value: "stopped",
      label: "На стопе (полностью)",
      short: "Стоп полн.",
      cls: "status-pill--stopped",
    },
  ];

  var CURRENCIES = [
    { value: "RUB", label: "Рубли", sign: "₽", short: "руб" },
    { value: "USD", label: "Доллары", sign: "$", short: "$" },
    { value: "UZS", label: "Узбекские сумы", sign: "сум", short: "сум" },
    { value: "KGS", label: "Киргизские сомы", sign: "сом", short: "сом" },
    { value: "KZT", label: "Казахские тенге", sign: "₸", short: "₸" },
    { value: "AZN", label: "Азербайджанские манаты", sign: "₼", short: "₼" },
    { value: "BYN", label: "Белорусские рубли", sign: "Br", short: "Br" },
    { value: "MDL", label: "Молдавские леи", sign: "lei", short: "lei" },
    { value: "PRB", label: "Приднестровские рубли", sign: "руб. ПМР", short: "руб. ПМР" },
  ];

  /* Блоки файлов в личных данных ноги. accept дублирует расширениями то, что
     не всякий Android отдаёт под нормальным MIME (HEIC с iPhone, .mov). */
  var NOGA_FILE_KINDS = [
    {
      value: "passport",
      label: "Фото паспорта",
      hint: "Разворот с фотографией",
      accept: "image/*,.heic,.heif,.avif,.jfif",
      video: false,
    },
    {
      value: "passport_selfie",
      label: "Паспорт и лицо",
      hint: "Нога держит паспорт рядом с лицом",
      accept: "image/*,.heic,.heif,.avif,.jfif",
      video: false,
    },
    {
      value: "face_video",
      label: "Короткое видео с лицом",
      hint: "Несколько секунд, лицо в кадре",
      accept: "video/*,.mov,.m4v,.3gp,.mkv",
      video: true,
    },
  ];

  /* Стадии трубки. Порядок тот же, что в жизни заказа. */
  var TRUBKA_STATUSES = [
    { value: "zacep", label: "Зацеп", cls: "trubka-status--zacep" },
    { value: "vedut", label: "Ведут", cls: "trubka-status--vedut" },
    { value: "srez", label: "Срез", cls: "trubka-status--srez" },
    { value: "zabrali", label: "Забрали", cls: "trubka-status--zabrali" },
    { value: "razgruzheno", label: "Разгружено", cls: "trubka-status--razgruzheno" },
  ];

  /* Как посылка попала к ноге. */
  var TRUBKA_DELIVERIES = [
    { value: "zahod", label: "Заход на адрес", hint: "Нога сама приехала к заказчику" },
    { value: "taxi", label: "Такси", hint: "Заказчик отправил посылку ноге на такси" },
  ];

  function find(list, value) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].value === value) return list[i];
    }
    return null;
  }

  function cityStatus(value) {
    return find(CITY_STATUSES, value) || CITY_STATUSES[0];
  }

  function currency(value) {
    return find(CURRENCIES, value);
  }

  function trubkaStatus(value) {
    return find(TRUBKA_STATUSES, value) || TRUBKA_STATUSES[0];
  }

  function trubkaDelivery(value) {
    return find(TRUBKA_DELIVERIES, value) || TRUBKA_DELIVERIES[0];
  }

  /** 200000 → «200 000» (тонкие пробелы, как в дашборде) */
  function formatNumber(value) {
    return String(Number(value) || 0).replace(/\B(?=(\d{3})+(?!\d))/g, "\u2009");
  }

  function formatAmount(amount, currencyCode) {
    if (amount === null || amount === undefined) return "не задан";
    var cur = currency(currencyCode);
    return formatNumber(amount) + (cur ? " " + cur.sign : "");
  }

  /** 200000 → «200к», 1500000 → «1,5м» — для компактных подписей на карточках. */
  function formatCompactNumber(value) {
    var n = Number(value) || 0;
    var abs = Math.abs(n);
    function trim(v) {
      var s = (Math.round(v * 10) / 10).toString().replace(".", ",");
      return s;
    }
    if (abs >= 1000000) return trim(n / 1000000) + "м";
    if (abs >= 1000) return trim(n / 1000) + "к";
    return formatNumber(n);
  }

  /** 200000 + RUB → «200к руб». null → пустая строка (на карточке не показываем). */
  function formatCompactAmount(amount, currencyCode) {
    if (amount === null || amount === undefined) return "";
    var cur = currency(currencyCode);
    var unit = cur ? cur.short || cur.sign : "";
    return formatCompactNumber(amount) + (unit ? " " + unit : "");
  }

  function formatDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  }

  /** 28.07.2026, 15:40 — для трубок, где важен и час */
  function formatDateTime(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return (
      d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" }) +
      ", " +
      d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
    );
  }

  /** 3.5 → «3,5 %» */
  function formatPercent(value) {
    var n = Number(value) || 0;
    return String(n).replace(".", ",") + " %";
  }

  /** 2516582 → «2,4 МБ» */
  function formatSize(bytes) {
    var n = Number(bytes) || 0;
    if (n < 1024) return n + " Б";
    if (n < 1024 * 1024) return (n / 1024).toFixed(0).replace(".", ",") + " КБ";
    return (n / (1024 * 1024)).toFixed(1).replace(".", ",") + " МБ";
  }

  function fileKind(value) {
    return find(NOGA_FILE_KINDS, value) || NOGA_FILE_KINDS[0];
  }

  global.NogaDict = {
    CITY_STATUSES: CITY_STATUSES,
    CURRENCIES: CURRENCIES,
    NOGA_FILE_KINDS: NOGA_FILE_KINDS,
    TRUBKA_STATUSES: TRUBKA_STATUSES,
    TRUBKA_DELIVERIES: TRUBKA_DELIVERIES,
    cityStatus: cityStatus,
    currency: currency,
    trubkaStatus: trubkaStatus,
    trubkaDelivery: trubkaDelivery,
    fileKind: fileKind,
    formatNumber: formatNumber,
    formatAmount: formatAmount,
    formatCompactNumber: formatCompactNumber,
    formatCompactAmount: formatCompactAmount,
    formatDate: formatDate,
    formatDateTime: formatDateTime,
    formatPercent: formatPercent,
    formatSize: formatSize,
  };
})(window);
