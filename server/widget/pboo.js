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

function loadWidget(siteId) {
  try {
    const markup = typeof WIDGET_MARKUP !== "undefined" ? WIDGET_MARKUP : "";
    const styles = typeof WIDGET_STYLES !== "undefined" ? WIDGET_STYLES : "";
    if (!markup || !styles) {
      throw new Error("widget assets are missing");
    }
    createWidget(siteId, markup, styles);
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
  let visitorToken = null;

  function addMessage(text, kind, includeTimestamp = true) {
    const message = document.createElement("div");
    message.className = `message ${kind}`;
    message.textContent = text;

    if (includeTimestamp && kind !== "system" && kind !== "typing") {
      const timestamp = document.createElement("div");
      timestamp.className = "timestamp";
      timestamp.textContent = formatTime(new Date());
      message.appendChild(timestamp);
    }

    messages.appendChild(message);
    messages.scrollTop = messages.scrollHeight;
  }

  function formatTime(date) {
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${hours}:${minutes}`;
  }

  function addTypingIndicator() {
    const existing = messages.querySelector(".message.typing");
    if (existing) existing.remove();

    const typing = document.createElement("div");
    typing.className = "message typing";
    typing.innerHTML =
      "<span class='typing-dot'></span><span class='typing-dot'></span><span class='typing-dot'></span>";
    messages.appendChild(typing);
    messages.scrollTop = messages.scrollHeight;
    return typing;
  }

  function removeTypingIndicator() {
    const typing = messages.querySelector(".message.typing");
    if (typing) typing.remove();
  }

  function updateStatus(text, type = "default") {
    const statusText = status.querySelector(".status-text");
    if (statusText) statusText.textContent = text;

    status.className = "status";
    if (type === "online") status.classList.add("online");
    else if (type === "typing") status.classList.add("typing");
  }

  function connect() {
    if (!visitorToken) return;
    if (socket && socket.readyState === WebSocket.OPEN) return;
    socket = new WebSocket(`${socketUrl}/ws/visitor/${siteId}`);
    socket.onopen = () => {
      status.textContent = "Connecting...";
      socket.send(
        JSON.stringify({
          type: "visitor.connected",
          visitor_token: visitorToken,
        }),
      );
    };
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "owner.status") {
          removeTypingIndicator();
          if (data.online) {
            updateStatus("Owner is online", "online");
            sendButton.disabled = false;
          } else {
            updateStatus("Owner is offline", "default");
            sendButton.disabled = true;
          }
          return;
        }
        if (data.type === "owner.message") {
          removeTypingIndicator();
          addMessage(data.message ?? event.data, "owner");
          return;
        }
      } catch {
        addMessage(event.data, "owner");
      }
    };
    socket.onerror = () => {
      updateStatus("Connection unavailable", "default");
      socket = null;
    };
    socket.onclose = () => {
      socket = null;
      updateStatus("Connecting...", "default");
    };
  }

  function sendMessage(text) {
    const body = {
      site_id: siteId,
      visitor_id: visitorId,
      message: text,
      page: window.location.pathname,
      referrer: document.referrer || "",
    };
    return fetch(`${serverUrl}/v1/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((resp) => {
        if (!resp.ok) throw new Error("send failed");
        return resp.json();
      })
      .then((data) => {
        // Reconnect with a fresh signed token once any previous one has expired.
        visitorToken = data.visitor_token || visitorToken;
        if (data.visitor_token && (!socket || socket.readyState !== WebSocket.OPEN)) {
          connect();
        }
      });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    sendMessage(text)
      .then(() => {
        addMessage(text, "visitor", true);
        input.value = "";
      })
      .catch(() => {
        updateStatus("Failed to send — try again", "default");
      });
  });

  launcher.addEventListener("click", () => {
    const isOpen = panel.classList.toggle("open");
    launcher.setAttribute("aria-expanded", String(isOpen));
    launcher.textContent = isOpen ? "x" : "+";
    if (isOpen) input.focus();
  });

  sendButton.disabled = false;
}

function getVisitorId() {
  const storedId = localStorage.getItem(visitorIdKey);
  if (storedId) return storedId;
  const newId = crypto.randomUUID();
  localStorage.setItem(visitorIdKey, newId);
  return newId;
}
