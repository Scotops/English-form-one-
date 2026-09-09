(function () {
  "use strict";

  var page = document.querySelector(".adt-book-page");
  var canvas = document.querySelector(".adt-page-canvas");
  var flow = document.querySelector(".adt-page-flow");
  if (!page || !canvas || !flow) return;

  function fitDesktopPage() {
    flow.style.width = "100%";
    flow.style.height = "auto";
    flow.style.transform = "none";
    if (window.innerWidth <= 767) return;

    var available = Math.max(100, canvas.clientHeight - 76);
    var scale = 1;
    for (var pass = 0; pass < 4; pass += 1) {
      flow.style.width = (100 / scale) + "%";
      var naturalHeight = Math.max(flow.scrollHeight, 1);
      scale = Math.min(1, available / naturalHeight);
    }
    flow.style.width = (100 / scale) + "%";
    flow.style.transform = "scale(" + scale + ")";
    flow.style.height = (flow.scrollHeight * scale) + "px";
    page.dataset.layoutScale = scale.toFixed(5);
  }

  var queued = false;
  function queueFit() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () {
      queued = false;
      fitDesktopPage();
    });
  }

  window.addEventListener("resize", queueFit, { passive: true });
  window.addEventListener("load", queueFit, { once: true });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(queueFit);
  new MutationObserver(queueFit).observe(flow, { childList: true, subtree: true, characterData: true });
  setTimeout(queueFit, 80);
  setTimeout(queueFit, 500);
})();
