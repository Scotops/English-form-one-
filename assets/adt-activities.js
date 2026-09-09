(function () {
  "use strict";

  var workspace = document.getElementById("adt-exercise-workspace");
  if (!workspace) return;
  var activities = Array.from(document.querySelectorAll("[data-activity-id]"));
  var toggle = workspace.querySelector(".adt-workspace-toggle");
  var panel = document.getElementById("adt-workspace-panel");
  var select = document.getElementById("adt-activity-select");
  var response = document.getElementById("adt-activity-response");
  var save = document.getElementById("adt-response-save");
  var clear = document.getElementById("adt-response-clear");
  var status = document.getElementById("adt-workspace-status");
  if (!activities.length || !toggle || !panel || !select || !response || !save || !clear || !status) return;

  function shortLabel(element, index) {
    var text = (element.innerText || element.textContent || "").replace(/\s+/g, " ").trim();
    var cue = text.match(/(?:Activity|Exercise|Task|Questions?)\s*\d*/i);
    return (cue && cue[0]) || ("Activity " + (index + 1));
  }

  var pageId = document.querySelector('meta[name="title-id"]')?.content || location.pathname;
  var records = activities.map(function (element, index) {
    var sourceId = element.dataset.activityId || ("activity-" + (index + 1));
    return { element: element, id: sourceId + "-" + index, label: shortLabel(element, index) };
  });

  records.forEach(function (record) {
    var option = document.createElement("option");
    option.value = record.id;
    option.textContent = record.label;
    select.appendChild(option);
  });

  function storageKey() { return "adt-response:" + pageId + ":" + select.value; }
  function load() {
    response.value = localStorage.getItem(storageKey()) || "";
    response.setAttribute("aria-label", "Your response for " + select.options[select.selectedIndex].textContent);
    status.textContent = "";
  }

  toggle.addEventListener("click", function () {
    var expanded = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!expanded));
    panel.hidden = expanded;
    if (!expanded) { load(); select.focus(); }
  });
  select.addEventListener("change", load);
  save.addEventListener("click", function () {
    localStorage.setItem(storageKey(), response.value);
    status.textContent = "Response saved on this device.";
  });
  clear.addEventListener("click", function () {
    localStorage.removeItem(storageKey());
    response.value = "";
    status.textContent = "Response cleared. You can try again.";
    response.focus();
  });
  load();
})();
