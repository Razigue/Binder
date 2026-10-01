// Applies the last known language and theme before React loads, so that the first frame is not
// drawn in the wrong theme. I18nProvider takes over once the preferences arrive. A separate file
// rather than an inline script: the Content-Security-Policy only allows same-origin scripts.
;(function () {
  var prefs = {}
  try {
    prefs = JSON.parse(localStorage.getItem("binder.preferences") || "{}") || {}
  } catch {
    // Storage unavailable or corrupt: system theme, English.
  }
  var root = document.documentElement
  var theme = prefs.theme
  var dark =
    theme === "dark" || (theme !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches)
  root.classList.toggle("dark", dark)
  root.style.colorScheme = dark ? "dark" : "light"
  root.lang = prefs.language === "fr" ? "fr" : "en"
})()
