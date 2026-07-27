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
    { value: "RUB", label: "Рубли", sign: "₽" },
    { value: "USD", label: "Доллары", sign: "$" },
    { value: "UZS", label: "Узбекские сумы", sign: "сум" },
    { value: "KGS", label: "Киргизские сомы", sign: "сом" },
    { value: "KZT", label: "Казахские тенге", sign: "₸" },
    { value: "AZN", label: "Азербайджанские манаты", sign: "₼" },
    { value: "BYN", label: "Белорусские рубли", sign: "Br" },
    { value: "MDL", label: "Молдавские леи", sign: "lei" },
    { value: "PRB", label: "Приднестровские рубли", sign: "руб. ПМР" },
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

  /** 200000 → «200 000» (тонкие пробелы, как в дашборде) */
  function formatNumber(value) {
    return String(Number(value) || 0).replace(/\B(?=(\d{3})+(?!\d))/g, "\u2009");
  }

  function formatAmount(amount, currencyCode) {
    if (amount === null || amount === undefined) return "не задан";
    var cur = currency(currencyCode);
    return formatNumber(amount) + (cur ? " " + cur.sign : "");
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
    cityStatus: cityStatus,
    currency: currency,
    fileKind: fileKind,
    formatNumber: formatNumber,
    formatAmount: formatAmount,
    formatDate: formatDate,
    formatPercent: formatPercent,
    formatSize: formatSize,
  };
})(window);
