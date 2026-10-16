function normalized(value) {
  return (value || "").normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

function setEditableText(element, value) {
  element.focus();
  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value");
    descriptor?.set?.call(element, value);
    element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  } else {
    document.execCommand("selectAll", false);
    if (!document.execCommand("insertText", false, value)) {
      element.replaceChildren(document.createTextNode(value));
      element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    }
  }
}

function findSearchBox() {
  const candidates = [...document.querySelectorAll('[contenteditable="true"], input')];
  return candidates.find((element) => {
    const label = `${element.getAttribute("aria-label") || ""} ${element.getAttribute("placeholder") || ""}`.toLowerCase();
    return /search|start a new chat|چیٹ تلاش|نئی چیٹ|تلاش/.test(label) && element.getClientRects().length > 0;
  });
}

function findNewChatButton() {
  const known = document.querySelector('[data-testid="chat-list-header-new-chat"], [data-testid="compose-btn-new-chat"]');
  if (known) return known;
  return [...document.querySelectorAll('button, [role="button"]')].find((element) => {
    const label = `${element.getAttribute("aria-label") || ""} ${element.getAttribute("title") || ""}`.toLowerCase();
    return /new chat|new conversation|new message|compose|نئی چیٹ|نئی گفتگو/.test(label);
  });
}

async function waitForSearchBox(timeoutMs = 3000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const search = findSearchBox();
    if (search) return search;
    await new Promise((resolve) => window.setTimeout(resolve, 200));
  }
  return null;
}

function findContactRows(contact) {
  const expected = normalized(contact);
  const chatRows = [...document.querySelectorAll('[data-testid="cell-frame-container"]')];
  const rows = chatRows.length ? chatRows : [...document.querySelectorAll('[role="listitem"]')];
  return rows.filter((row) => {
    const title = row.querySelector("[title]")?.getAttribute("title");
    const ariaLabel = row.getAttribute("aria-label");
    const visibleName = normalized(title || ariaLabel || row.innerText?.split("\n")[0]);
    return visibleName === expected;
  });
}

async function waitForContact(contact, timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const matches = findContactRows(contact);
    if (matches.length) return matches;
    await new Promise((resolve) => window.setTimeout(resolve, 250));
  }
  return [];
}

function conversationName() {
  const header = document.querySelector('[data-testid="conversation-header"]');
  const name = header?.querySelector("[title]")?.getAttribute("title") || header?.innerText?.split("\n")[0];
  return normalized(name);
}

function findComposer() {
  const preferred = document.querySelector('[data-testid="conversation-compose-box-input"]');
  if (preferred) return preferred;
  return [...document.querySelectorAll('[contenteditable="true"]')].find((element) => {
    const label = (element.getAttribute("aria-label") || "").toLowerCase();
    return /type a message|message/.test(label) && !/search/.test(label);
  });
}

let preparedDraft = null;

async function prepareMessage(message) {
  const contact = String(message.contact || "").trim();
  const text = String(message.text || "").trim();
  if (!contact || !text) {
    return {
      type: "whatsapp_prepared",
      requestId: message.requestId,
      ok: false,
      message: "The contact name or message was empty; nothing was sent."
    };
  }

  let matches = findContactRows(contact);
  if (matches.length > 1) {
    return {
      type: "whatsapp_prepared",
      requestId: message.requestId,
      ok: false,
      message: `More than one WhatsApp chat matches ${contact}. Use a unique full contact name; nothing was sent.`
    };
  }
  let row = matches[0] || null;
  if (!row) {
    let search = findSearchBox();
    if (search) {
      setEditableText(search, contact);
      matches = await waitForContact(contact, 3500);
      if (matches.length > 1) {
        return {
          type: "whatsapp_prepared",
          requestId: message.requestId,
          ok: false,
          message: `More than one WhatsApp contact matches ${contact}. Use a unique full contact name; nothing was sent.`
        };
      }
      row = matches[0] || null;
    }
    if (!row) {
      const newChat = findNewChatButton();
      if (newChat) {
        if (search) setEditableText(search, "");
        newChat.click();
        search = await waitForSearchBox();
        if (search) {
          setEditableText(search, contact);
          matches = await waitForContact(contact);
          if (matches.length > 1) {
            return {
              type: "whatsapp_prepared",
              requestId: message.requestId,
              ok: false,
              message: `More than one WhatsApp contact matches ${contact}. Use a unique full contact name; nothing was sent.`
            };
          }
          row = matches[0] || null;
        }
      }
    }
  }
  if (!row) {
    return {
      type: "whatsapp_prepared",
      requestId: message.requestId,
      ok: false,
      message: `Could not find an exact WhatsApp chat named ${contact}. Nothing was sent.`
    };
  }

  row.click();
  const expected = normalized(contact);
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline && conversationName() !== expected) {
    await new Promise((resolve) => window.setTimeout(resolve, 150));
  }
  if (conversationName() !== expected) {
    return {
      type: "whatsapp_prepared",
      requestId: message.requestId,
      ok: false,
      message: `WhatsApp did not open the exact chat for ${contact}. Nothing was sent.`
    };
  }

  const composer = findComposer();
  if (!composer) {
    return {
      type: "whatsapp_prepared",
      requestId: message.requestId,
      ok: false,
      message: "Could not find the WhatsApp message box. Nothing was sent."
    };
  }
  setEditableText(composer, text);
  preparedDraft = { requestId: message.requestId, contact, text };
  return {
    type: "whatsapp_prepared",
    requestId: message.requestId,
    ok: true
  };
}

function clearDraftIfMatching() {
  if (!preparedDraft || conversationName() !== normalized(preparedDraft.contact)) {
    preparedDraft = null;
    return;
  }
  const composer = findComposer();
  if (composer && normalized(composer.innerText) === normalized(preparedDraft.text)) {
    setEditableText(composer, "");
  }
  preparedDraft = null;
}

function confirmMessage(message) {
  if (!preparedDraft || preparedDraft.requestId !== message.requestId) {
    return {
      type: "whatsapp_error",
      requestId: message.requestId,
      message: "The prepared message could not be verified; nothing was sent."
    };
  }
  if (
    normalized(preparedDraft.contact) !== normalized(message.contact) ||
    conversationName() !== normalized(preparedDraft.contact)
  ) {
    clearDraftIfMatching();
    return {
      type: "whatsapp_error",
      requestId: message.requestId,
      message: "The WhatsApp chat changed after confirmation; nothing was sent."
    };
  }
  const composer = findComposer();
  if (!composer || normalized(composer.innerText) !== normalized(preparedDraft.text)) {
    preparedDraft = null;
    return {
      type: "whatsapp_error",
      requestId: message.requestId,
      message: "The message draft changed after confirmation; nothing was sent."
    };
  }
  const sendButton = document.querySelector('[data-testid="compose-btn-send"], button[aria-label^="Send"]');
  if (!sendButton || sendButton.disabled) {
    return {
      type: "whatsapp_error",
      requestId: message.requestId,
      message: "WhatsApp's send button is unavailable; nothing was sent."
    };
  }
  sendButton.click();
  preparedDraft = null;
  return {
    type: "whatsapp_sent",
    requestId: message.requestId,
    message: "The confirmed message was sent."
  };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "prepare_whatsapp") {
    prepareMessage(message).then(sendResponse).catch(() => sendResponse({
      type: "whatsapp_prepared",
      requestId: message.requestId,
      ok: false,
      message: "WhatsApp could not prepare the draft. Nothing was sent."
    }));
    return true;
  }
  if (message?.type === "confirm_whatsapp") {
    sendResponse(confirmMessage(message));
    return false;
  }
  if (message?.type === "cancel_whatsapp") {
    if (preparedDraft?.requestId === message.requestId) clearDraftIfMatching();
    return false;
  }
  return false;
});

chrome.runtime.sendMessage({ type: "whatsapp_content_ready" });
