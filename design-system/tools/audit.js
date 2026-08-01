"use strict";
/* Статическая проверка дизайн-системы: неизвестные токены, классы без стилей,
   отсутствующие иконки, баланс тегов и скобок, хардкод цвета, кегли вне шкалы,
   запрещённая терминология. Запуск: node design-system/tools/audit.js */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..");
const read = (f) => fs.readFileSync(path.join(root, f), "utf8");

const tokens = read("tokens.css");
const base = read("base.css");
const comp = read("components.css");
const show = read("showcase.css");
const html = read("index.html");
const icons = read("icons.js");
const ds = read("ds.js");

let fail = 0;
const bad = (msg) => { console.log("FAIL " + msg); fail++; };
const ok = (msg) => console.log("ok   " + msg);

/* 1. Токены */
const defined = new Set([...tokens.matchAll(/(--em-[\w-]+)\s*:/g)].map((m) => m[1]));
const used = new Set([...(base + comp + show + html + ds).matchAll(/var\((--em-[\w-]+)/g)].map((m) => m[1]));
const setProps = new Set([...(base + comp + show + html + ds).matchAll(/(--em-[\w-]+)\s*:/g)].map((m) => m[1]));
const unknown = [...used].filter((t) => !defined.has(t) && !setProps.has(t));
unknown.length
  ? bad("неизвестные токены: " + unknown.join(", "))
  : ok("токены: все " + used.size + " ссылок определены (" + defined.size + " объявлено)");

/* Неиспользованные — не ошибка: шкалы (spacing, оттенки золота, z-слои)
   держим полными, чтобы новые компоненты не изобретали значения. */
const unusedTokens = [...defined].filter((t) => !used.has(t));
console.log("     резерв шкалы, пока не использован: " + (unusedTokens.length ? unusedTokens.join(", ") : "нет"));

/* 2. Классы */
const cssClasses = new Set(
  [...(base + comp + show).matchAll(/\.((?:em|doc|sw|spec|icons|type|ruler|box-demo|screens|hero-mock|fix)[\w-]*)/g)].map((m) => m[1])
);
const htmlClasses = new Set();
[...html.matchAll(/class="([^"]+)"/g)].forEach((m) => m[1].split(/\s+/).forEach((c) => c && htmlClasses.add(c)));
const missing = [...htmlClasses].filter(
  (c) => !cssClasses.has(c) && /^(em|doc|sw|spec|icons|type|ruler|screens|hero-mock|fix)/.test(c)
);
missing.length
  ? bad("классы в разметке без стилей: " + missing.join(", "))
  : ok("классы: все " + htmlClasses.size + " из разметки определены в CSS");

/* 3. Иконки */
const iconNames = new Set([...icons.matchAll(/^\s{4}"?([a-z-]+)"?:\s*'/gm)].map((m) => m[1]));
iconNames.add("logo");
const iconUse = new Set([...html.matchAll(/data-em-icon="([\w-]+)"/g)].map((m) => m[1]));
[...ds.matchAll(/icon:\s*"([\w-]+)"/g)].forEach((m) => iconUse.add(m[1]));
const noIcon = [...iconUse].filter((n) => !iconNames.has(n));
noIcon.length
  ? bad("иконки не найдены в наборе: " + noIcon.join(", "))
  : ok("иконки: все " + iconUse.size + " использованных есть в наборе (" + iconNames.size + " всего)");

/* 4. Баланс тегов в HTML */
const voids = new Set(["meta", "link", "br", "hr", "img", "input", "source", "use", "path", "circle", "rect", "stop"]);
const stack = [];
let balanced = true;
for (const m of html.matchAll(/<(\/?)([a-zA-Z][\w-]*)([^>]*?)(\/?)>/g)) {
  const [, close, tag, , selfClose] = m;
  if (voids.has(tag) || selfClose) continue;
  if (!close) stack.push(tag);
  else {
    const top = stack.pop();
    if (top !== tag) {
      bad("несбалансированный тег: закрыт </" + tag + ">, открыт <" + top + ">");
      balanced = false;
      break;
    }
  }
}
if (balanced && stack.length) bad("не закрыты теги: " + stack.join(", "));
if (balanced && !stack.length) ok("HTML: теги сбалансированы");

/* 5. Баланс фигурных скобок в CSS */
[["tokens.css", tokens], ["base.css", base], ["components.css", comp], ["showcase.css", show]].forEach(([name, css]) => {
  const open = (css.match(/{/g) || []).length;
  const close = (css.match(/}/g) || []).length;
  if (open !== close) bad(name + ": скобки " + open + " { против " + close + " }");
});
ok("CSS: скобки сбалансированы");

/* 6. Хардкод цвета вне tokens.css. Замеры в комментариях и переопределения
   токенов внутри @media — не хардкод. */
const hexIn = (name, css) => {
  const clean = css
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/--em-[\w-]+\s*:/.test(line))
    .join("\n");
  const hits = [...clean.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((m) => m[0]);
  if (hits.length) bad(name + ": hex вне токенов — " + [...new Set(hits)].join(", "));
  else ok(name + ": hex-цветов нет");
};
hexIn("components.css", comp);
hexIn("base.css", base);

/* 7. transition: all */
if (/transition:\s*all/.test(comp + base)) bad("найден transition: all");
else ok("transition: all не используется");

/* 8. Кегли вне шкалы */
const sizes = [...comp.matchAll(/font-size:\s*([\d.]+)px/g)].map((m) => m[1]);
sizes.length ? bad("font-size в px в components.css: " + sizes.join(", ")) : ok("кегли только из шкалы токенов");

/* 9. Запрещённое слово */
if (/курьер/i.test(tokens + base + comp + show + html + icons + ds)) bad("встречается слово «курьер»");
else ok("терминология: «курьер» не встречается");

console.log(fail ? "\n" + fail + " проблем(ы)" : "\nвсё чисто");
process.exit(fail ? 1 : 0);
