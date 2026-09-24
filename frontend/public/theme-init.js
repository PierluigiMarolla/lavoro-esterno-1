(function () {
  "use strict";
  var stored = localStorage.getItem("lavoro_esterno_theme");
  var isDark =
    stored === "dark" ||
    (stored !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", isDark);
})();
