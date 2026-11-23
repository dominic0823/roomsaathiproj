document.addEventListener("DOMContentLoaded", function () {

  document.querySelectorAll(".toast-wrap .alert").forEach(function (a, i) {
    setTimeout(function () { a.style.transition = "opacity .4s, transform .4s"; a.style.opacity = "0"; a.style.transform = "translateX(30px)"; setTimeout(function () { a.remove(); }, 450); }, 5500 + i * 600);
    a.addEventListener("click", function () { a.remove(); });
  });

  const header = document.querySelector(".site-header");
  if (header) { const f = function () { header.classList.toggle("scrolled", window.scrollY > 6); }; f(); window.addEventListener("scroll", f, { passive: true }); }

  const toggle = document.querySelector(".nav-toggle"), nav = document.querySelector(".main-nav");
  if (toggle && nav) toggle.addEventListener("click", function () { nav.classList.toggle("open"); });

  document.addEventListener("click", function (e) { document.querySelectorAll("details.user-menu[open]").forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute("open"); }); });

  document.querySelectorAll("select[data-autosubmit]").forEach(function (s) { s.addEventListener("change", function () { s.form.submit(); }); });
  const ft = document.getElementById("filter-toggle"), fp = document.getElementById("filter-panel");
  if (ft && fp) ft.addEventListener("click", function () { fp.classList.toggle("open"); });
  document.querySelectorAll(".chip[data-max]").forEach(function (b) {
    b.addEventListener("click", function () {
      const f = b.closest("form"); f.querySelector("[name=min_price]").value = ""; f.querySelector("[name=max_price]").value = b.dataset.max; f.submit();
    });
  });
});
