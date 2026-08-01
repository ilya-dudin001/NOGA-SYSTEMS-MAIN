/* ============================================================
   EM 3.5 — Operations. Поведение компонентов
   Ванильный JS, ES5-совместимый стиль (как в assets/js/*).
   Экспорт: window.EmDS. Инициализация — EmDS.init(root).
   Каждый блок независим: если разметки нет, ничего не делает.
   ============================================================ */
(function (global) {
  "use strict";

  var doc = global.document;

  function all(sel, root) {
    return Array.prototype.slice.call((root || doc).querySelectorAll(sel));
  }

  function emit(node, name, detail) {
    var ev;
    try {
      ev = new CustomEvent(name, { detail: detail, bubbles: true });
    } catch (e) {
      ev = doc.createEvent("CustomEvent");
      ev.initCustomEvent(name, true, false, detail);
    }
    node.dispatchEvent(ev);
  }

  function reduced() {
    return global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  /* ---------- 1. Табы-фильтры -------------------------------- */
  function bindTabs(root) {
    all("[data-em-tabs]", root).forEach(function (group) {
      var tabs = all('[role="tab"]', group);
      group.addEventListener("click", function (e) {
        var btn = e.target.closest ? e.target.closest('[role="tab"]') : null;
        if (!btn || btn.disabled || tabs.indexOf(btn) === -1) return;
        tabs.forEach(function (t) {
          t.setAttribute("aria-selected", t === btn ? "true" : "false");
          t.tabIndex = t === btn ? 0 : -1;
        });
        btn.scrollIntoView({ block: "nearest", inline: "nearest", behavior: reduced() ? "auto" : "smooth" });
        emit(group, "em:tabchange", { value: btn.getAttribute("data-value"), tab: btn });
      });
      /* Клавиатура: стрелки листают табы — иначе с клавиатуры
         фильтр недоступен */
      group.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        var i = tabs.indexOf(doc.activeElement);
        if (i === -1) return;
        e.preventDefault();
        var next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        next.focus();
        next.click();
      });
    });
  }

  /* ---------- 2. Сегментированный переключатель --------------- */
  function bindSegmented(root) {
    all("[data-em-seg]", root).forEach(function (seg) {
      var btns = all("[data-em-seg-btn]", seg);
      seg.style.setProperty("--em-seg-count", String(btns.length));
      function select(btn, silent) {
        var index = btns.indexOf(btn);
        if (index === -1) return;
        seg.style.setProperty("--em-seg-index", String(index));
        btns.forEach(function (b) {
          b.setAttribute("aria-selected", b === btn ? "true" : "false");
        });
        if (!silent) emit(seg, "em:segchange", { value: btn.getAttribute("data-value"), index: index });
      }
      btns.forEach(function (btn) {
        btn.addEventListener("click", function () { select(btn); });
      });
      var pre = btns.filter(function (b) { return b.getAttribute("aria-selected") === "true"; })[0];
      select(pre || btns[0], true);
    });
  }

  /* ---------- 3. Нижняя навигация ---------------------------- */
  function bindTabbar(root) {
    all("[data-em-tabbar]", root).forEach(function (bar) {
      var tabs = all("[data-em-navtab]", bar);
      bar.addEventListener("click", function (e) {
        var btn = e.target.closest ? e.target.closest("[data-em-navtab]") : null;
        if (!btn || tabs.indexOf(btn) === -1) return;
        tabs.forEach(function (t) {
          if (t === btn) t.setAttribute("aria-current", "page");
          else t.removeAttribute("aria-current");
        });
        emit(bar, "em:navchange", { value: btn.getAttribute("data-value") });
      });
    });
  }

  /* ---------- 4. Загрузка фото ------------------------------- */
  function bindUpload(root) {
    all("[data-em-upload]", root).forEach(function (block) {
      var input = block.querySelector('input[type="file"]');
      var status = block.querySelector("[data-em-upload-status]");
      var progress = block.querySelector("[data-em-progress]");
      var bar = progress ? progress.querySelector(".em-progress__bar") : null;
      var host = block.querySelector("[data-em-upload-preview]");
      if (!input) return;

      input.addEventListener("change", function () {
        var file = input.files && input.files[0];
        if (!file) return;
        block.classList.remove("is-error", "is-done");
        block.classList.add("is-uploading");
        if (progress) progress.hidden = false;
        if (status) status.textContent = "Загрузка…";

        /* Прогресс здесь демонстрационный: в приложении его двигает
           XHR/fetch, разметка и классы те же */
        var pct = 0;
        var step = global.setInterval(function () {
          pct = Math.min(100, pct + 18 + Math.random() * 14);
          if (bar) bar.style.width = pct + "%";
          if (pct < 100) return;
          global.clearInterval(step);
          block.classList.remove("is-uploading");
          block.classList.add("is-done");
          if (status) status.textContent = "Добавлено";
          if (progress) global.setTimeout(function () { progress.hidden = true; if (bar) bar.style.width = "0"; }, 260);
          if (host && /^image\//.test(file.type)) {
            var url = URL.createObjectURL(file);
            host.hidden = false;
            host.innerHTML = "";
            var img = doc.createElement("img");
            img.alt = "Предпросмотр загруженного фото";
            img.src = url;
            /* Каждый createObjectURL обязательно отзываем */
            img.onload = function () { URL.revokeObjectURL(url); };
            img.onerror = function () {
              URL.revokeObjectURL(url);
              block.classList.add("is-error");
              if (status) status.textContent = "Не удалось открыть файл — скачайте его";
            };
            host.appendChild(img);
          }
          emit(block, "em:upload", { file: file });
        }, 220);
      });
    });
  }

  /* ---------- 5. Копирование номера операции ------------------ */
  function bindCopy(root) {
    all("[data-em-copy]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        var value = btn.getAttribute("data-em-copy");
        var done = function () {
          btn.classList.add("is-success");
          var live = btn.querySelector("[data-em-copy-live]");
          if (live) live.textContent = "Номер скопирован";
          global.setTimeout(function () {
            btn.classList.remove("is-success");
            if (live) live.textContent = "";
          }, 1600);
        };
        if (global.navigator.clipboard && global.navigator.clipboard.writeText) {
          global.navigator.clipboard.writeText(value).then(done, done);
        } else {
          done();
        }
      });
    });
  }

  /* ---------- 6. Статус операции: «в работе» ↔ «дома» --------- */
  var STATUS = {
    work: { mod: "work", label: "В работе", icon: "dot-ring" },
    home: { mod: "home", label: "Дома", icon: "home" },
    wait: { mod: "wait", label: "Ждёт подтверждения", icon: "clock" },
    paid: { mod: "paid", label: "Выплачено", icon: "check-circle" },
    done: { mod: "done", label: "Подтверждено", icon: "check" },
    payout: { mod: "payout", label: "Выплата", icon: "arrow-down-circle" },
    left: { mod: "left", label: "Осталось", icon: "pause-circle" }
  };

  function setStatus(pill, key) {
    var next = STATUS[key];
    if (!next) return;
    Object.keys(STATUS).forEach(function (k) { pill.classList.remove("em-pill--" + STATUS[k].mod); });
    pill.classList.add("em-pill--" + next.mod);
    var label = pill.querySelector("[data-em-status-label]");
    var icon = pill.querySelector("[data-em-status-icon]");
    if (label) label.textContent = next.label;
    if (icon && global.EmIcons) icon.innerHTML = global.EmIcons.svg(next.icon);
    pill.setAttribute("data-status", key);
  }

  function bindStatusToggle(root) {
    all("[data-em-status-toggle]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        var pill = doc.querySelector(btn.getAttribute("data-em-status-toggle"));
        if (!pill) return;
        var order = (btn.getAttribute("data-em-status-order") || "work,home").split(",");
        var current = pill.getAttribute("data-status") || order[0];
        var next = order[(order.indexOf(current) + 1) % order.length];
        setStatus(pill, next);
        emit(pill, "em:statuschange", { status: next });
      });
    });
  }

  /* ---------- 7. Появление при скролле ----------------------- */
  function bindReveal(root) {
    var nodes = all(".em-reveal--wait", root);
    if (!nodes.length) return;
    if (!global.IntersectionObserver || reduced()) {
      nodes.forEach(function (n) { n.classList.add("is-in"); });
      return;
    }
    var io = new global.IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-in");
        io.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: .05 });
    nodes.forEach(function (n) { io.observe(n); });
  }

  /* ---------- 8. Каскад: раздаём --i детям ------------------- */
  function bindStagger(root) {
    all("[data-em-stagger]", root).forEach(function (host) {
      Array.prototype.forEach.call(host.children, function (child, i) {
        if (!child.style.getPropertyValue("--i")) child.style.setProperty("--i", String(i));
      });
    });
  }

  /* ---------- 9. Кнопка с ожиданием ответа ------------------- */
  function bindAsyncButtons(root) {
    all("[data-em-async]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.classList.contains("is-loading")) return;
        var mode = btn.getAttribute("data-em-async");
        btn.classList.add("is-loading");
        btn.setAttribute("aria-busy", "true");
        global.setTimeout(function () {
          btn.classList.remove("is-loading");
          btn.removeAttribute("aria-busy");
          btn.classList.add(mode === "error" ? "is-error" : "is-success");
          global.setTimeout(function () { btn.classList.remove("is-success", "is-error"); }, 1500);
        }, 1100);
      });
    });
  }

  /* ---------- 10. Переключение экранов ---------------------- */
  function bindScreens(root) {
    all("[data-em-goto]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        show(btn.getAttribute("data-em-goto"));
      });
    });
  }

  function show(id) {
    var target = doc.getElementById(id);
    if (!target) return;
    all("[data-em-screen]").forEach(function (screen) {
      screen.hidden = screen !== target;
    });
    /* Перезапуск анимации входа */
    target.classList.remove("em-screen");
    void target.offsetWidth;
    target.classList.add("em-screen");
    emit(target, "em:screenshow", { id: id });
  }

  /* ---------- 11. Валидация формы (демо) -------------------- */
  function bindValidate(root) {
    all("[data-em-validate]", root).forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var ok = true;
        all("[data-em-required]", form).forEach(function (field) {
          var control = field.querySelector("input, select");
          var empty = !control || !String(control.value || "").trim();
          field.classList.toggle("is-error", empty);
          if (control) control.setAttribute("aria-invalid", empty ? "true" : "false");
          if (empty) ok = false;
        });
        var first = form.querySelector(".is-error input, .is-error select");
        if (first) first.focus();
        emit(form, "em:submit", { valid: ok });
      });
      form.addEventListener("input", function (e) {
        var field = e.target.closest ? e.target.closest("[data-em-required]") : null;
        if (field && String(e.target.value || "").trim()) {
          field.classList.remove("is-error");
          e.target.setAttribute("aria-invalid", "false");
        }
      });
    });
  }

  function init(root) {
    if (global.EmIcons) {
      global.EmIcons.mount(doc);
      global.EmIcons.hydrate(root || doc);
    }
    bindTabs(root);
    bindSegmented(root);
    bindTabbar(root);
    bindUpload(root);
    bindCopy(root);
    bindStatusToggle(root);
    bindStagger(root);
    bindReveal(root);
    bindAsyncButtons(root);
    bindScreens(root);
    bindValidate(root);
  }

  global.EmDS = {
    init: init,
    show: show,
    setStatus: setStatus,
    STATUS: STATUS
  };

  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", function () { init(doc); });
  else init(doc);
})(window);
