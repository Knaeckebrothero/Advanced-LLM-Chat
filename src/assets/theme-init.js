// The theme's class before the app starts, so a dark theme doesn't flash white; ThemeService takes over.
// A file, not an inline script: the Content-Security-Policy allows scripts from the app's own files only.
(function () {
  var stored = null;
  try { stored = localStorage.getItem('theme-preference'); } catch (e) {}
  var dark = stored === 'dark' || (stored !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.body.classList.add(dark ? 'theme-dark' : 'theme-light');
})();
