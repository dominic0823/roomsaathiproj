document.addEventListener("DOMContentLoaded", function () {
  const panel = document.getElementById("slot-panel");
  if (!panel) return;

  const list = document.getElementById("slot-list");
  const empty = document.getElementById("no-slots");
  const canBook = panel.dataset.canBook === "1";
  const csrfInput = document.querySelector("#csrf-holder input[name=csrfmiddlewaretoken]");
  const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
  let retry = 0;

  function refreshEmpty() {
    empty.hidden = list.querySelectorAll(".slot-row").length > 0;
  }

  function removeRow(id) {
    const row = document.getElementById("slot-" + id);
    if (row) row.remove();
    refreshEmpty();
  }

  function buildRow(data) {
    const row = document.createElement("div");
    row.className = "slot-row live";
    row.id = "slot-" + data.slot_id;
    row.dataset.sort = data.sort_key;

    const label = document.createElement("span");
    label.textContent = data.label;
    row.appendChild(label);

    if (canBook && csrfInput) {
      const f = document.createElement("form");
      f.method = "post";
      f.action = data.book_url;
      const t = document.createElement("input");
      t.type = "hidden"; t.name = "csrfmiddlewaretoken"; t.value = csrfInput.value;
      const b = document.createElement("button");
      b.type = "submit"; b.className = "btn btn-primary btn-sm"; b.textContent = "Book visit";
      f.appendChild(t); f.appendChild(b);
      row.appendChild(f);
    } else if (!canBook && panel.dataset.loginUrl && !csrfInput) {
      const a = document.createElement("a");
      a.href = panel.dataset.loginUrl; a.className = "btn btn-primary btn-sm"; a.textContent = "Log in to book";
      row.appendChild(a);
    }
    return row;
  }

  function addRow(data) {
    if (document.getElementById("slot-" + data.slot_id)) return;
    const row = buildRow(data);
    const rows = Array.from(list.querySelectorAll(".slot-row"));
    const after = rows.find(function (r) { return r.dataset.sort > data.sort_key; });
    list.insertBefore(row, after || empty);
    refreshEmpty();
  }

  function connect() {
    const socket = new WebSocket(protocol + window.location.host + "/ws/availability/" + panel.dataset.serviceId + "/");
    socket.onopen = function () { retry = 0; };
    socket.onmessage = function (event) {
      const data = JSON.parse(event.data);
      if (data.is_booked) {

        const row = document.getElementById("slot-" + data.slot_id);
        if (row) {
          row.classList.remove("live"); row.classList.add("taken");
          row.querySelectorAll("form, a").forEach(function (n) { n.remove(); });
          const tag = document.createElement("span");
          tag.className = "slot-tag taken-tag"; tag.textContent = "Just booked";
          row.appendChild(tag);
          setTimeout(function () { removeRow(data.slot_id); }, 2500);
        }
      } else {
        addRow(data);
      }
    };
    socket.onclose = function () { setTimeout(connect, Math.min(1000 * Math.pow(2, retry++), 15000)); };
  }
  connect();
});
