document.addEventListener("DOMContentLoaded", function () {
  const chatWindow = document.getElementById("chat-window");
  if (!chatWindow) return;

  const roomId = chatWindow.dataset.roomId;
  const me = JSON.parse(document.getElementById("current-username").textContent);
  const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
  const url = protocol + window.location.host + "/ws/chat/" + roomId + "/";

  const messagesBox = document.getElementById("chat-messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const status = document.getElementById("chat-status");

  let socket, retry = 0, denied = false;

  function addMessage(sender, content, timestamp) {
    const div = document.createElement("div");
    div.className = "chat-message" + (sender === me ? " mine" : "");
    [["chat-sender", sender], ["chat-text", content], ["chat-time", timestamp]].forEach(function (p) {
      const span = document.createElement("span");
      span.className = p[0];
      span.textContent = p[1];
      div.appendChild(span);
    });
    messagesBox.appendChild(div);
    messagesBox.scrollTop = messagesBox.scrollHeight;
  }

  function connect() {
    socket = new WebSocket(url);
    socket.onopen = function () { retry = 0; status.hidden = true; };
    socket.onmessage = function (event) {
      const data = JSON.parse(event.data);
      if (data.error) { status.textContent = data.error; status.hidden = false; return; }
      addMessage(data.sender, data.message, data.timestamp);
    };
    socket.onclose = function (e) {
      if (e.code === 4403 || e.code === 4401) {
        denied = true;
        status.textContent = "This chat is no longer available.";
        status.hidden = false;
        return;
      }
      status.textContent = "Reconnecting…";
      status.hidden = false;
      setTimeout(connect, Math.min(1000 * Math.pow(2, retry++), 15000));
    };
  }
  connect();

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const value = input.value.trim();
    if (!value || denied || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ message: value }));
    input.value = "";
  });

  messagesBox.scrollTop = messagesBox.scrollHeight;
});
