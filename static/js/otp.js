document.addEventListener("DOMContentLoaded", function () {
  const wrap = document.getElementById("otp-boxes");
  if (wrap) {
    const hidden = document.getElementById("otp-code"), btn = document.getElementById("otp-submit"), form = document.getElementById("otp-form");
    const boxes = [];
    for (let i = 0; i < 6; i++) {
      const b = document.createElement("input");
      b.type = "text"; b.inputMode = "numeric"; b.maxLength = 1; b.autocomplete = i === 0 ? "one-time-code" : "off";
      b.setAttribute("aria-label", "Digit " + (i + 1)); b.className = "otp-box";
      wrap.appendChild(b); boxes.push(b);
    }
    function sync() {
      const code = boxes.map(function (b) { return b.value; }).join("");
      hidden.value = code; btn.disabled = code.length !== 6;
      boxes.forEach(function (b) { b.classList.toggle("filled", !!b.value); });
      if (code.length === 6) setTimeout(function () { if (!btn.disabled) form.submit(); }, 250);
    }
    boxes.forEach(function (b, i) {
      b.addEventListener("input", function () {
        b.value = b.value.replace(/\D/g, "").slice(-1);
        if (b.value && i < 5) boxes[i + 1].focus();
        sync();
      });
      b.addEventListener("keydown", function (e) {
        if (e.key === "Backspace" && !b.value && i > 0) { boxes[i - 1].value = ""; boxes[i - 1].focus(); sync(); }
        if (e.key === "ArrowLeft" && i > 0) boxes[i - 1].focus();
        if (e.key === "ArrowRight" && i < 5) boxes[i + 1].focus();
      });
      b.addEventListener("paste", function (e) {
        const text = (e.clipboardData || window.clipboardData).getData("text").replace(/\D/g, "").slice(0, 6);
        if (!text) return;
        e.preventDefault();
        text.split("").forEach(function (d, k) { boxes[k].value = d; });
        boxes[Math.min(text.length, 5)].focus(); sync();
      });
      b.addEventListener("focus", function () { b.select(); });
    });
    boxes[0].focus();
    const fill = document.getElementById("demo-fill");
    if (fill) fill.addEventListener("click", function () {
      fill.dataset.code.split("").forEach(function (d, k) { boxes[k].value = d; });
      sync();
    });
  }

  const exp = document.getElementById("otp-expiry");
  if (exp) {
    let left = parseInt(exp.dataset.seconds, 10) || 0;
    const label = exp.querySelector("b");
    (function tick() {
      if (left <= 0) { exp.innerHTML = "This code has expired. Please request a new one below."; exp.classList.add("expired"); return; }
      label.textContent = String(Math.floor(left / 60)).padStart(2, "0") + ":" + String(left % 60).padStart(2, "0");
      left--; setTimeout(tick, 1000);
    })();
  }

  const rs = document.getElementById("otp-resend");
  if (rs) {
    let wait = parseInt(rs.dataset.wait, 10) || 0;
    const text = document.getElementById("resend-text"), btns = rs.querySelectorAll(".resend-btn");
    (function tick() {
      if (wait <= 0) { text.textContent = "Didn't get it?"; btns.forEach(function (b) { b.disabled = false; }); return; }
      text.textContent = "You can request another code in " + wait + "s";
      wait--; setTimeout(tick, 1000);
    })();
  }
});
