(function () {
  "use strict";

  var page = document.getElementById("content");
  if (!page) return;

  function fit() {
    page.style.transform = "none";
    page.style.marginBottom = "0";
    if (window.innerWidth <= 700) return;
    var width = Number.parseFloat(getComputedStyle(page).getPropertyValue("--page-width")) || page.offsetWidth;
    var height = Number.parseFloat(getComputedStyle(page).getPropertyValue("--page-height")) || page.offsetHeight;
    var scale = Math.min(1, Math.max(0.5, (window.innerWidth - 24) / width));
    if (scale >= 0.999) return;
    page.style.transform = "scale(" + scale.toFixed(5) + ")";
    page.style.marginBottom = (-height * (1 - scale)).toFixed(2) + "px";
  }

  var queued = false;
  function queue() {
    if (queued) return;
    queued = true;
    window.requestAnimationFrame(function () {
      queued = false;
      fit();
    });
  }

  window.addEventListener("resize", queue, { passive: true });
  window.addEventListener("load", queue, { once: true });
  queue();
})();
