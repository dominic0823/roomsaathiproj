document.addEventListener("DOMContentLoaded", function () {
  const tabs = document.querySelectorAll(".tab[data-tab]");
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      tabs.forEach(function (t) { t.classList.toggle("active", t === tab); });
      document.querySelectorAll(".tab-pane").forEach(function (pane) {
        pane.hidden = pane.id !== "pane-" + tab.dataset.tab;
      });
    });
  });
  if (location.hash === "#visit") { const t = document.querySelector('.tab[data-tab="visit"]'); if (t) t.click(); }

  const share = document.getElementById("share-btn");
  if (share) share.addEventListener("click", function () {
    const data = { title: share.dataset.title, url: location.href.split("#")[0] };
    if (navigator.share) { navigator.share(data).catch(function () {}); return; }
    window.open("https://wa.me/?text=" + encodeURIComponent(data.title + " - " + data.url), "_blank");
  });
});
