const SERVER_URL = "ws://127.0.0.1:8765";
const WHATSAPP_URL = "https://web.whatsapp.com/";
let localSocket = null;
let reconnectTimer = 0;
let pendingAction = null;
let dispatchInProgress = false;

function sendToLocalServer(message) {
  if (localSocket?.readyState === WebSocket.OPEN) {
    localSocket.send(JSON.stringify(message));
  }
}

function connectLocalServer() {
  if (localSocket?.readyState === WebSocket.OPEN || localSocket?.readyState === WebSocket.CONNECTING) return;
  try {
    const socket = new WebSocket(SERVER_URL);
    localSocket = socket;
    socket.addEventListener("open", () => {
      clearTimeout(reconnectTimer);
      socket.send(JSON.stringify({ type: "register_whatsapp" }));
    });
    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.type === "open_whatsapp") {
        openWhatsapp();
      } else if (message.type === "prepare_whatsapp") {
        pendingAction = message;
        openWhatsapp().then(dispatchPendingAction);
      } else if (message.type === "confirm_whatsapp" || message.type === "cancel_whatsapp") {
        sendActionToWhatsapp(message);
      }
    });
    socket.addEventListener("close", () => {
      if (localSocket === socket) localSocket = null;
      scheduleReconnect();
    });
    socket.addEventListener("error", () => socket.close());
  } catch {
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connectLocalServer, 5000);
}

async function openWhatsapp() {
  const tabs = await chrome.tabs.query({ url: "https://web.whatsapp.com/*" });
  if (tabs.length) {
    const tab = tabs[0];
    if (tab.id !== undefined) {
      await chrome.tabs.update(tab.id, { active: true });
      await chrome.windows.update(tab.windowId, { focused: true });
      return tab.id;
    }
  }
  const tab = await chrome.tabs.create({ url: WHATSAPP_URL, active: true });
  return tab.id;
}

async function dispatchPendingAction() {
  if (!pendingAction || dispatchInProgress) return;
  const tabs = await chrome.tabs.query({ url: "https://web.whatsapp.com/*" });
  const tab = tabs[0];
  if (!tab?.id) return;
  dispatchInProgress = true;
  const action = pendingAction;
  try {
    let response;
    for (let attempt = 0; attempt < 30; attempt += 1) {
      if (pendingAction !== action) return;
      try {
        response = await chrome.tabs.sendMessage(tab.id, action);
        if (response) break;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 400));
      }
    }
    if (pendingAction === action) {
      pendingAction = null;
      sendToLocalServer(response || {
        type: "whatsapp_error",
        requestId: action.requestId,
        message: "WhatsApp Web did not become ready. Make sure it is open and logged in, then try again."
      });
    }
  } finally {
    dispatchInProgress = false;
    if (pendingAction) dispatchPendingAction();
  }
}

async function sendActionToWhatsapp(action) {
  const tabs = await chrome.tabs.query({ url: "https://web.whatsapp.com/*" });
  if (!tabs[0]?.id) {
    sendToLocalServer({
      type: "whatsapp_error",
      requestId: action.requestId,
      message: "WhatsApp Web is not open; the message was not sent."
    });
    return;
  }
  try {
    const response = await chrome.tabs.sendMessage(tabs[0].id, action);
    if (response) sendToLocalServer(response);
  } catch {
    sendToLocalServer({
      type: "whatsapp_error",
      requestId: action.requestId,
      message: "The WhatsApp tab is not ready; the message was not sent."
    });
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("jarvis-local-server", { periodInMinutes: 0.5 });
  connectLocalServer();
});
chrome.runtime.onStartup.addListener(connectLocalServer);
chrome.alarms.onAlarm.addListener(connectLocalServer);
chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url?.startsWith(WHATSAPP_URL)) {
    dispatchPendingAction();
  }
});
chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "whatsapp_content_ready") {
    connectLocalServer();
    dispatchPendingAction();
  }
});

connectLocalServer();
