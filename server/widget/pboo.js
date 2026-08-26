const currentScript = document.currentScript;
const siteId = currentScript?.dataset.site;
const assetRoot = currentScript
  ? new URL(".", currentScript.src)
  : new URL("http://localhost:8000/widget/");
const serverUrl = assetRoot.origin;
const socketUrl = serverUrl.replace(/^http/, "ws");
const visitorIdKey = `peekaboo-visitor-${siteId}`;
const visitorId = getVisitorId();

if (!siteId) {
  console.error("Peekaboo: data-site is missing");
} else {
  loadWidget(siteId);
}

async function loadWidget(siteId) {
  try {
    const [markupResponse, stylesResponse] = await Promise.all([
      fetch(new URL("widget.html", assetRoot)),
      fetch(new URL("styles.css", assetRoot)),
    ]);
    if (!markupResponse.ok || !stylesResponse.ok) {
      throw new Error("widget assets returned an error");
    }
    createWidget(
      siteId,
      await markupResponse.text(),
      await stylesResponse.text(),
    );
  } catch (error) {
    console.error("Peekaboo: could not load widget assets", error);
  }
}

function createWidget(siteId, markup, styles) {
  const host = document.createElement("div");
  host.setAttribute("aria-label", "Peekaboo chat");
  document.body.appendChild(host);

  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `<style>${styles}</style>${markup}`;

  const launcher = root.querySelector(".launcher");
  const panel = root.querySelector(".panel");
  const status = root.querySelector(".status");
  const messages = root.querySelector(".messages");
  const form = root.querySelector("form");
  const input = root.querySelector("input");
  const sendButton = root.querySelector("form button");
  let socket;
  let statusTimer;

  function addMessage(text, kind) {
    const message = document.createElement("div");
    message.className = `message ${kind}`;
    message.textContent = text;
    messages.appendChild(message);
    messages.scrollTop = messages.scrollHeight;
  }

  async function checkOwnerStatus() {
    try {
      const response = await fetch(
        `${serverUrl}/sites/${encodeURIComponent(siteId)}/status`,
        { cache: "no-store" },
      );
      if (!response.ok) throw new Error("status request failed");
      const data = await response.json();
      if (data.operator_online) {
        status.textContent = "Owner is online";
        if (!socket || socket.readyState === WebSocket.CLOSED) connect();
      } else {
        status.textContent = "Owner is offline";
        sendButton.disabled = true;
        if (socket) {
          socket.close();
          socket = null;
        }
      }
    } catch {
      status.textContent = "Chat unavailable";
      sendButton.disabled = true;
    }
    clearTimeout(statusTimer);
    statusTimer = setTimeout(checkOwnerStatus, 15000);
  }

  function connect() {
    socket = new WebSocket(`${socketUrl}/ws/visitor/${siteId}`);
    socket.onopen = () => {
      status.textContent = "Online now";
      sendButton.disabled = false;
      socket.send(
        JSON.stringify({
          type: "visitor.connected",
          visitor_id: visitorId,
          page: window.location.pathname,
        }),
      );
    };
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        addMessage(data.message ?? event.data, "owner");
      } catch {
        addMessage(event.data, "owner");
      }
    };
    socket.onerror = () => {
      status.textContent = "Connection unavailable";
    };
    socket.onclose = () => {
      status.textContent = "Owner is offline";
      sendButton.disabled = true;
      socket = null;
      clearTimeout(statusTimer);
      statusTimer = setTimeout(checkOwnerStatus, 15000);
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
  checkOwnerStatus();
}

function getVisitorId() {
  const storedId = localStorage.getItem(visitorIdKey);
  if (storedId) return storedId;
  const newId = crypto.randomUUID();
  localStorage.setItem(visitorIdKey, newId);
  return newId;
}
