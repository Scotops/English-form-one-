(function () {
  "use strict";

  // Word highlighting is a core reading aid for this edition. Set both
  // persistence stores before the ADT runtime initializes so an older local
  // preference cannot silently leave it in sentence mode.
  try {
    window.localStorage.setItem("wordHighlightMode", "true");
  } catch (_error) {
    // Storage can be unavailable in some embedded readers; the runtime's
    // default is already word mode in that case.
  }
  document.cookie = "wordHighlightMode=true; Max-Age=31536000; Path=/; SameSite=Lax";

  function startFacsimileHighlight() {
    var content = document.getElementById("content");
    var pageCard = document.querySelector(".adt-page-card");
    if (!content || !pageCard) return;

    var sourcePage = Number.parseInt(content.getAttribute("data-source-pdf-page") || "", 10);
    if (!Number.isFinite(sourcePage)) return;

    var marker = document.createElement("span");
    marker.className = "adt-page-word-highlight";
    marker.setAttribute("aria-hidden", "true");
    pageCard.appendChild(marker);

    var wordMap = null;
    var syncQueued = false;

    function hideIndicators() {
      marker.classList.remove("is-visible");
    }

    function showBox(box) {
      marker.style.left = (box[0] * 100).toFixed(4) + "%";
      marker.style.top = (box[1] * 100).toFixed(4) + "%";
      marker.style.width = (box[2] * 100).toFixed(4) + "%";
      marker.style.height = (box[3] * 100).toFixed(4) + "%";
      marker.classList.add("is-visible");
    }

    function syncHighlight() {
      syncQueued = false;
      var activeWord = content.querySelector("[data-word-index].bg-yellow-300");
      if (!activeWord) {
        hideIndicators();
        return;
      }

      var textElement = activeWord.closest("[data-id]");
      var textId = textElement && textElement.getAttribute("data-id");
      var wordIndex = Number.parseInt(activeWord.getAttribute("data-word-index") || "", 10);
      var box =
        wordMap &&
        textId &&
        Number.isFinite(wordIndex) &&
        wordMap.items &&
        wordMap.items[textId] &&
        wordMap.items[textId][wordIndex];

      if (Array.isArray(box) && box.length === 4) {
        showBox(box);
      } else {
        hideIndicators();
      }
    }

    function queueSync() {
      if (syncQueued) return;
      syncQueued = true;
      window.requestAnimationFrame(syncHighlight);
    }

    var observer = new MutationObserver(queueSync);
    observer.observe(content, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["class"],
    });

    var pageKey = String(sourcePage).padStart(3, "0");
    fetch("./content/word-boxes/pg" + pageKey + ".json?v=1")
      .then(function (response) {
        if (!response.ok) throw new Error("Word box map unavailable");
        return response.json();
      })
      .then(function (data) {
        wordMap = data;
        queueSync();
      })
      .catch(function () {
        wordMap = { items: {} };
        queueSync();
      });

    window.addEventListener("pagehide", function () {
      observer.disconnect();
    }, { once: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startFacsimileHighlight, { once: true });
  } else {
    startFacsimileHighlight();
  }
})();
