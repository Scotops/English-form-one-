(function () {
  "use strict";

  try {
    window.localStorage.setItem("wordHighlightMode", "true");
  } catch (_error) {
    // The reader defaults to word mode when storage is unavailable.
  }
  document.cookie = "wordHighlightMode=true; Max-Age=31536000; Path=/; SameSite=Lax";

  function start() {
    var content = document.getElementById("content");
    var marker = content && content.querySelector(".adt-tts-source-word-highlight");
    var mapNode = document.getElementById("adt-word-highlight-map");
    if (!content || !marker || !mapNode) return;

    var wordMap = {};
    try {
      wordMap = JSON.parse(mapNode.textContent || "{}");
    } catch (_error) {
      wordMap = {};
    }

    var queued = false;
    function hide() {
      marker.classList.remove("is-active");
    }

    function synchronize() {
      queued = false;
      var activeWord = content.querySelector("[data-word-index].bg-yellow-300");
      if (!activeWord) {
        hide();
        return;
      }
      var textElement = activeWord.closest("[data-id]");
      var textId = textElement && textElement.getAttribute("data-id");
      var wordIndex = Number.parseInt(activeWord.getAttribute("data-word-index") || "", 10);
      var box = textId && Number.isFinite(wordIndex) && wordMap[textId] && wordMap[textId][wordIndex];
      if (!Array.isArray(box) || box.length !== 4) {
        hide();
        return;
      }
      marker.style.left = box[0].toFixed(3) + "px";
      marker.style.top = box[1].toFixed(3) + "px";
      marker.style.width = box[2].toFixed(3) + "px";
      marker.style.height = box[3].toFixed(3) + "px";
      marker.classList.add("is-active");
    }

    function queue() {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(synchronize);
    }

    var observer = new MutationObserver(queue);
    observer.observe(content, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["class"],
    });
    queue();
    window.addEventListener("pagehide", function () { observer.disconnect(); }, { once: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
