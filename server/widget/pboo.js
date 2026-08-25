const currentScript = document.currentScript;
const siteId = currentScript?.dataset.site;
const SERVER_URL = currentScript
  ? new URL(currentScript.src).origin.replace(/^http/, "ws")
  : "ws://localhost:8000";

if (!siteId) {
  console.error("Peekaboo: data-site is missing");
} else {
  createWidget(siteId);
}

function createWidget(siteId) {
  const host = document.createElement("div");
  host.setAttribute("aria-label", "Peekaboo chat");
  document.body.appendChild(host);

  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `
    <style>
      :host { all: initial; }
      * { box-sizing: border-box; }
      .launcher {
        position: fixed; right: 24px; bottom: 24px; z-index: 2147483647;
        width: 58px; height: 58px; border: 0; border-radius: 50%;
        background: #e85d3f; color: white; font: 700 24px system-ui;
        cursor: pointer; box-shadow: 0 10px 26px #17212b40;
      }
      .panel {
        position: fixed; right: 24px; bottom: 94px; z-index: 2147483647;
        display: none; flex-direction: column; width: min(360px, calc(100vw - 32px));
        height: min(520px, calc(100vh - 120px)); overflow: hidden;
        border: 1px solid #dce4e8; border-radius: 18px; background: #fff;
        color: #17212b; font: 15px system-ui; box-shadow: 0 18px 50px #17212b2e;
      }
      .panel.open { display: flex; }
      header { padding: 18px 20px; background: #17212b; color: #fff; }
      header strong { display: block; font-size: 17px; }
      header span { color: #b9c8ce; font-size: 12px; }
      .messages { display: flex; flex: 1; flex-direction: column; gap: 10px; padding: 16px; overflow-y: auto; background: #f5f8f8; }
      .message { max-width: 82%; padding: 10px 12px; border-radius: 13px; line-height: 1.35; overflow-wrap: anywhere; }
      .visitor { align-self: flex-end; border-bottom-right-radius: 4px; background: #e85d3f; color: #fff; }
      .owner { align-self: flex-start; border-bottom-left-radius: 4px; background: #fff; border: 1px solid #dce4e8; }
      form { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #dce4e8; background: #fff; }
      input { min-width: 0; flex: 1; padding: 10px 12px; border: 1px solid #c7d3d8; border-radius: 9px; font: inherit; outline-color: #e85d3f; }
      form button { border: 0; border-radius: 9px; padding: 0 14px; background: #17212b; color: #fff; font-weight: 700; cursor: pointer; }
      form button:disabled { cursor: not-allowed; opacity: .5; }
      @media (max-width: 480px) { .launcher { right: 16px; bottom: 16px; } .panel { right: 16px; bottom: 88px; } }
    </style>
    <button class="launcher" type="button" aria-expanded="false" aria-label="Open chat">+</button>
    <section class="panel" aria-label="Chat with the website owner">
      <header><strong>Chat with us</strong><span class="status">Connecting...</span></header>
      <div class="messages" aria-live="polite"><div class="message owner">Hi! How can we help?</div></div>
      <form><input aria-label="Message" placeholder="Write a message..." autocomplete="off" /><button type="submit">Send</button></form>
    </section>
  `;

  const launcher = root.querySelector(".launcher");
  const panel = root.querySelector(".panel");
  const status = root.querySelector(".status");
  const messages = root.querySelector(".messages");
  const form = root.querySelector("form");
  const input = root.querySelector("input");
  const sendButton = root.querySelector("form button");
  let socket;

  function addMessage(text, kind) {
    const message = document.createElement("div");
    message.className = `message ${kind}`;
    message.textContent = text;
    messages.appendChild(message);
    messages.scrollTop = messages.scrollHeight;
  }

  function connect() {
    socket = new WebSocket(`${SERVER_URL}/ws/visitor/${siteId}`);
    socket.onopen = () => {
      status.textContent = "Online now";
      sendButton.disabled = false;
      socket.send(
        JSON.stringify({
          type: "visitor.connected",
          page: window.location.pathname,
        }),
      );
    };
    socket.onmessage = (event) => addMessage(event.data, "owner");
    socket.onerror = () => {
      status.textContent = "Connection unavailable";
    };
    socket.onclose = () => {
      status.textContent = "Offline";
      sendButton.disabled = true;
    };
  }

  launcher.addEventListener("click", () => {
    const isOpen = panel.classList.toggle("open");
    launcher.setAttribute("aria-expanded", String(isOpen));
    launcher.textContent = isOpen ? "x" : "+";
    if (isOpen) input.focus();
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || !socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(text);
    addMessage(text, "visitor");
    input.value = "";
  });

  sendButton.disabled = true;
  connect();
}
