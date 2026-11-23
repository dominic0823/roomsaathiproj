document.addEventListener("DOMContentLoaded", function () {
  const pv = document.getElementById("pano-viewer");
  if (pv && window.pannellum) {
    let viewer;
    const load = function (src) {
      if (viewer) viewer.destroy();
      viewer = window.pannellum.viewer("pano-viewer", { type: "equirectangular", panorama: src, autoLoad: true, autoRotate: -2, showZoomCtrl: true, showFullscreenCtrl: true, hfov: 105, crossOrigin: "anonymous" });
    };
    load(pv.dataset.src);
    document.querySelectorAll(".pano-tab").forEach(function (tab, i) {
      if (i === 0) tab.classList.add("active");
      tab.addEventListener("click", function () {
        document.querySelectorAll(".pano-tab").forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active"); load(tab.dataset.src);
      });
    });
  }
  const items = Array.from(document.querySelectorAll("[data-lightbox]"));
  const box = document.getElementById("lightbox");
  if (!items.length || !box) return;
  const img = box.querySelector("img"), count = box.querySelector(".lb-count");
  let i = 0;
  const srcs = items.map(function (el) { return el.dataset.lightbox; });
  function show(n) { i = (n + srcs.length) % srcs.length; img.src = srcs[i]; count.textContent = (i + 1) + " / " + srcs.length; }
  function open(n) { show(n); box.classList.add("open"); document.body.style.overflow = "hidden"; }
  function close() { box.classList.remove("open"); document.body.style.overflow = ""; }
  items.forEach(function (el, n) { el.addEventListener("click", function () { open(n); }); });
  const all = document.getElementById("gallery-all"); if (all) all.addEventListener("click", function () { open(0); });
  box.querySelector(".lb-close").addEventListener("click", close);
  box.querySelector(".lb-prev").addEventListener("click", function () { show(i - 1); });
  box.querySelector(".lb-next").addEventListener("click", function () { show(i + 1); });
  box.addEventListener("click", function (e) { if (e.target === box) close(); });
  document.addEventListener("keydown", function (e) { if (!box.classList.contains("open")) return; if (e.key === "Escape") close(); if (e.key === "ArrowLeft") show(i - 1); if (e.key === "ArrowRight") show(i + 1); });
});
