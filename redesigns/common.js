(function () {
  "use strict";

  var tabs = document.querySelectorAll("[data-view-target]");
  var views = document.querySelectorAll("[data-view]");
  var filters = document.querySelectorAll("[data-filter]");
  var rows = document.querySelectorAll("[data-status]");
  var createButton = document.querySelector("[data-create]");
  var sheet = document.querySelector("[data-sheet]");
  var sheetClose = document.querySelectorAll("[data-sheet-close]");
  var toast = document.querySelector("[data-toast]");

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 1800);
  }

  Array.prototype.forEach.call(tabs, function (tab) {
    tab.addEventListener("click", function () {
      var target = tab.getAttribute("data-view-target");
      Array.prototype.forEach.call(tabs, function (item) {
        var active = item.getAttribute("data-view-target") === target;
        item.classList.toggle("is-active", active);
        if (active) {
          item.setAttribute("aria-current", "page");
        } else {
          item.removeAttribute("aria-current");
        }
      });
      Array.prototype.forEach.call(views, function (view) {
        view.hidden = view.getAttribute("data-view") !== target;
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  Array.prototype.forEach.call(filters, function (filter) {
    filter.addEventListener("click", function () {
      var value = filter.getAttribute("data-filter");
      Array.prototype.forEach.call(filters, function (item) {
        item.classList.toggle("is-active", item === filter);
      });
      Array.prototype.forEach.call(rows, function (row) {
        row.hidden = value !== "all" && row.getAttribute("data-status") !== value;
      });
    });
  });

  if (createButton && sheet) {
    createButton.addEventListener("click", function () {
      sheet.hidden = false;
      window.requestAnimationFrame(function () {
        sheet.classList.add("is-open");
      });
    });
  }

  Array.prototype.forEach.call(sheetClose, function (button) {
    button.addEventListener("click", function () {
      if (!sheet) return;
      sheet.classList.remove("is-open");
      window.setTimeout(function () {
        sheet.hidden = true;
      }, 220);
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll("[data-demo-action]"), function (button) {
    button.addEventListener("click", function () {
      showToast(button.getAttribute("data-demo-action"));
    });
  });
})();
