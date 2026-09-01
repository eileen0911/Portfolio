const messagesEl = document.querySelector("#messages");
const optionTrayEl = document.querySelector("#optionTray");
const formEl = document.querySelector("#chatForm");
const inputEl = document.querySelector("#messageInput");
const sendButtonEl = document.querySelector("#sendButton");
const resetButtonEl = document.querySelector("#resetButton");
const sessionMetaEl = document.querySelector("#sessionMeta");
const statusBannerEl = document.querySelector("#statusBanner");
const sourcePanelEl = document.querySelector("#sourcePanel");
const sourcesListEl = document.querySelector("#sourcesList");
const sourceCloseButtonEl = document.querySelector("#sourceCloseButton");

const storageKey = "rag-demo-chat-session";
const sessionStorageRef = window.sessionStorage;
const config = window.CHATBOT_FRONTEND_CONFIG || {};
const query = new URLSearchParams(window.location.search);
const chatApiBaseUrl = trimTrailingSlash(
  query.get("chat_api_base_url") || config.chatApiBaseUrl || "",
);
const chatEndpoint = `${chatApiBaseUrl}/v1/chat`;

let sessionId = sessionStorageRef.getItem(storageKey) || "";
let pending = false;
let inputEnabled = false;
let lockedForTimeout = false;

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = inputEl.value.trim();
  if (!message || pending || !inputEnabled || lockedForTimeout) return;

  inputEl.value = "";
  appendMessage("user", message);
  await sendChatRequest({ action: "message", message, stream: true }, { stream: true });
});

resetButtonEl.addEventListener("click", () => {
  startFaq({ newSession: true });
});

sourceCloseButtonEl.addEventListener("click", () => {
  sourcePanelEl.hidden = true;
});

startFaq({ newSession: !sessionId });

async function startFaq({ newSession }) {
  if (newSession || !sessionId) {
    sessionId = crypto.randomUUID();
    sessionStorageRef.setItem(storageKey, sessionId);
  }

  lockedForTimeout = false;
  messagesEl.replaceChildren();
  optionTrayEl.replaceChildren();
  hideStatus();
  renderSources([]);
  setInputEnabled(false);
  setSessionMeta("FAQ");
  await sendChatRequest({ action: "start_faq" });
}

async function selectOption(option) {
  if (pending || lockedForTimeout) return;
  appendMessage("user", option.label);
  await sendChatRequest({ action: "select_option", option_id: option.id });
}

async function sendChatRequest(payload, { stream = false } = {}) {
  setPending(true);
  const pendingMessage = stream ? appendPendingMessage() : null;

  try {
    const response = await fetch(chatEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        locale: "zh-TW",
        ...payload,
      }),
    });

    const body = response.headers.get("content-type")?.includes("text/event-stream")
      ? await parseStreamingResponse(response, pendingMessage)
      : await response.json();

    if (!response.ok) {
      throw new Error(apiErrorMessage(response, body));
    }
    if (!body) {
      throw new Error("Empty response");
    }

    sessionId = body.session_id || sessionId;
    sessionStorageRef.setItem(storageKey, sessionId);
    renderResponse(body, pendingMessage);
  } catch (error) {
    optionTrayEl.replaceChildren();
    setInputEnabled(false);
    replacePendingMessage(pendingMessage, `Service unavailable: ${error.message}`);
    showStatus("Service unavailable. Please try again later.", "error");
    setSessionMeta("Service error");
  } finally {
    setPending(false);
  }
}

function renderResponse(body, pendingMessage) {
  hideStatus();

  if (!pendingMessage && body.answer) {
    appendMessage(messageRole(body), body.answer, body.cta);
  } else if (pendingMessage && body.answer) {
    replacePendingMessage(pendingMessage, body.answer, messageRole(body), body.cta);
  } else if (pendingMessage) {
    pendingMessage.remove();
  }

  renderOptions(body.options || []);
  renderSources(body.sources || []);

  if (body.status === "session_timeout" || body.error_code === "session_timeout") {
    renderSessionTimeout();
  } else if (body.status === "no_result") {
    showStatus("No matching knowledge-base source was found. You can revise the question and try again.", "notice");
    setInputEnabled(Boolean(body.input_enabled));
  } else if (body.status === "service_error") {
    showStatus("The support service could not complete this request. You can try again later.", "error");
    setInputEnabled(Boolean(body.input_enabled));
  } else {
    setInputEnabled(Boolean(body.input_enabled));
  }

  setSessionMeta(modeLabel(body));
}

function renderOptions(options) {
  optionTrayEl.replaceChildren();

  for (const option of options) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "option-button";
    button.textContent = option.label;
    button.disabled = pending || lockedForTimeout;
    button.addEventListener("click", () => selectOption(option));
    optionTrayEl.appendChild(button);
  }
}

function renderSessionTimeout() {
  lockedForTimeout = true;
  renderOptions([]);
  renderSources([]);
  setInputEnabled(false);
  showStatus("Session timeout. Please start a new session.", "warning");

  const button = document.createElement("button");
  button.type = "button";
  button.className = "option-button primary";
  button.textContent = "Start new session";
  button.addEventListener("click", () => startFaq({ newSession: true }));
  optionTrayEl.appendChild(button);
}

function renderSources(sources) {
  sourcesListEl.replaceChildren();
  sourcePanelEl.hidden = sources.length === 0;

  for (const source of sources) {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    const meta = document.createElement("span");
    const text = document.createElement("p");

    title.textContent = source.title || "Untitled source";
    meta.textContent = sourceMeta(source);
    text.textContent = source.text || "";
    item.append(title, meta, text);
    sourcesListEl.appendChild(item);
  }
}

function sourceMeta(source) {
  const parts = [];
  if (source.book_name) parts.push(source.book_name);
  if (source.source_category) parts.push(source.source_category);
  if (source.chunk_index !== null && source.chunk_index !== undefined) {
    parts.push(`Chunk ${source.chunk_index}`);
  }
  if (Number.isFinite(Number(source.score))) {
    parts.push(`Score ${Number(source.score).toFixed(3)}`);
  }
  return parts.join(" / ");
}

function appendMessage(role, text, cta = null) {
  const item = document.createElement("article");
  item.className = `message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  renderMessageContent(bubble, text, role);
  item.appendChild(bubble);
  renderCta(item, cta);

  messagesEl.appendChild(item);
  scrollToLatest();
  return item;
}

function messageRole(body) {
  return body.mode === "system" || body.status === "session_timeout" ? "system" : "assistant";
}

function appendPendingMessage() {
  const item = document.createElement("article");
  item.className = "message assistant pending";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = "";

  const loader = document.createElement("span");
  loader.className = "typing";
  loader.setAttribute("aria-hidden", "true");
  loader.innerHTML = "<span></span><span></span><span></span>";

  bubble.appendChild(loader);
  item.appendChild(bubble);
  messagesEl.appendChild(item);
  scrollToLatest();
  return item;
}

function replacePendingMessage(item, text, role = "assistant", cta = null) {
  if (!item) {
    appendMessage(role, text, cta);
    return;
  }
  item.className = `message ${role}`;
  renderMessageContent(item.querySelector(".bubble"), text, role);
  renderCta(item, cta);
  scrollToLatest();
}

function renderCta(messageItem, cta) {
  messageItem.querySelector(".cta-tray")?.remove();
  if (!isSupportedCta(cta)) return;

  const tray = document.createElement("div");
  tray.className = "cta-tray";

  const button = document.createElement("button");
  button.type = "button";
  button.className = "cta-button";
  button.textContent = cta.label;
  button.addEventListener("click", () => handleCta(cta));

  tray.appendChild(button);
  messageItem.appendChild(tray);
}

function isSupportedCta(cta) {
  if (!cta || typeof cta !== "object") return false;
  if (!cta.label || !cta.url_key || !cta.target) return false;
  if (cta.type === "external_url") {
    return cta.target === "_blank" && /^https?:\/\//.test(cta.url || "");
  }
  if (cta.type === "official_site_nav") {
    return cta.target === "parent" && Boolean(cta.nav_key) && isRelativeNavPath(cta.path);
  }
  return false;
}

function handleCta(cta) {
  if (cta.type === "external_url") {
    window.open(cta.url, "_blank", "noopener,noreferrer");
    return;
  }

  if (cta.type === "official_site_nav") {
    if (window.parent === window) {
      showStatus("This navigation action is only available when embedded in the official site.", "notice");
      return;
    }

    window.parent.postMessage(
      {
        type: "chatbot:navigate",
        nav_key: cta.nav_key,
        path: cta.path,
      },
      parentTargetOrigin(),
    );
  }
}

function parentTargetOrigin() {
  const configured = query.get("parent_origin") || config.parentOrigin || "";
  if (configured) return configured;
  try {
    return new URL(document.referrer).origin;
  } catch {
    return "*";
  }
}

function isRelativeNavPath(path) {
  if (!path || typeof path !== "string") return false;
  if (path.startsWith("/") || path.startsWith("./") || path.startsWith("../")) return true;
  return /^[A-Za-z0-9._/-]+(?:\?[A-Za-z0-9._~:/?#[\]@!$&'()*+,;=%-]*)?$/.test(path);
}

function renderMessageContent(container, text, role) {
  container.replaceChildren();
  container.classList.toggle("markdown", role !== "user");
  if (role === "user") {
    container.textContent = text;
    return;
  }

  for (const block of markdownBlocks(text)) {
    container.appendChild(block);
  }
}

function markdownBlocks(text) {
  const normalized = String(text || "").replace(/\r\n/g, "\n").trim();
  if (!normalized) return [document.createTextNode("")];

  const blocks = [];
  const lines = normalized.split("\n");
  let index = 0;

  while (index < lines.length) {
    if (!lines[index].trim()) {
      index += 1;
      continue;
    }

    const orderedMatch = lines[index].match(/^\s*\d+[.)]\s+(.+)$/);
    const unorderedMatch = lines[index].match(/^\s*[-*]\s+(.+)$/);
    if (orderedMatch || unorderedMatch) {
      const list = document.createElement(orderedMatch ? "ol" : "ul");
      while (index < lines.length) {
        const match = orderedMatch
          ? lines[index].match(/^\s*\d+[.)]\s+(.+)$/)
          : lines[index].match(/^\s*[-*]\s+(.+)$/);
        if (!match) break;
        const item = document.createElement("li");
        appendInlineMarkdown(item, match[1]);
        list.appendChild(item);
        index += 1;
      }
      blocks.push(list);
      continue;
    }

    const paragraphLines = [];
    while (
      index < lines.length
      && lines[index].trim()
      && !lines[index].match(/^\s*\d+[.)]\s+(.+)$/)
      && !lines[index].match(/^\s*[-*]\s+(.+)$/)
    ) {
      paragraphLines.push(lines[index]);
      index += 1;
    }

    const paragraph = document.createElement("p");
    paragraphLines.forEach((line, lineIndex) => {
      if (lineIndex > 0) paragraph.appendChild(document.createElement("br"));
      appendInlineMarkdown(paragraph, line);
    });
    blocks.push(paragraph);
  }

  return blocks;
}

function appendInlineMarkdown(parent, text) {
  const pattern = /(\[[^\]\n]+\]\((?:https?:\/\/|mailto:)[^)\s]+\)|\*\*[^*]+\*\*|`[^`]+`|\*[^*\n]+\*)/g;
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > offset) {
      parent.appendChild(document.createTextNode(text.slice(offset, match.index)));
    }

    const token = match[0];
    let element;
    let content;
    if (token.startsWith("[")) {
      const link = token.match(/^\[([^\]\n]+)\]\(((?:https?:\/\/|mailto:)[^)\s]+)\)$/);
      if (!link) {
        parent.appendChild(document.createTextNode(token));
        offset = match.index + token.length;
        continue;
      }
      element = document.createElement("a");
      element.href = link[2];
      element.target = "_blank";
      element.rel = "noopener noreferrer";
      content = link[1];
    } else if (token.startsWith("**")) {
      element = document.createElement("strong");
      content = token.slice(2, -2);
    } else if (token.startsWith("`")) {
      element = document.createElement("code");
      content = token.slice(1, -1);
    } else {
      element = document.createElement("em");
      content = token.slice(1, -1);
    }
    element.textContent = content;
    parent.appendChild(element);
    offset = match.index + token.length;
  }

  if (offset < text.length) {
    parent.appendChild(document.createTextNode(text.slice(offset)));
  }
}

async function parseStreamingResponse(response, pendingMessage) {
  if (!response.body) return null;

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let answer = "";
  let finalBody = null;
  let streamError = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      const event = parseSseEvent(block);
      if (!event) continue;

      if (event.event === "delta") {
        answer += event.data.content || "";
        replacePendingMessage(pendingMessage, answer);
      } else if (event.event === "sources") {
        renderSources(event.data || []);
      } else if (event.event === "final") {
        finalBody = event.data;
      } else if (event.event === "error") {
        streamError = event.data;
      }
    }
  }

  if (!finalBody && streamError) {
    throw new Error(streamError.message || streamError.code || "Streaming failed");
  }
  if (finalBody && answer && !finalBody.answer) {
    finalBody.answer = answer;
  }
  return finalBody;
}

function parseSseEvent(block) {
  const lines = block.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event:"));
  const dataLines = lines.filter((line) => line.startsWith("data:"));
  if (!eventLine || dataLines.length === 0) return null;

  try {
    return {
      event: eventLine.slice(6).trim(),
      data: JSON.parse(dataLines.map((line) => line.slice(5).trimStart()).join("\n")),
    };
  } catch {
    return null;
  }
}

function setPending(isPending) {
  pending = isPending;
  messagesEl.setAttribute("aria-busy", String(isPending));
  resetButtonEl.disabled = isPending;
  sendButtonEl.disabled = isPending || !inputEnabled || lockedForTimeout;
  inputEl.disabled = isPending || !inputEnabled || lockedForTimeout;
  for (const button of optionTrayEl.querySelectorAll("button")) {
    button.disabled = isPending || (lockedForTimeout && !button.classList.contains("primary"));
  }
}

function setInputEnabled(isEnabled) {
  inputEnabled = isEnabled && !lockedForTimeout;
  inputEl.disabled = pending || !inputEnabled;
  sendButtonEl.disabled = pending || !inputEnabled;
  inputEl.placeholder = inputEnabled ? "Type your question" : "";
  if (inputEnabled) inputEl.focus();
}

function setSessionMeta(text) {
  const shortId = sessionId ? sessionId.slice(0, 8) : "new";
  sessionMetaEl.textContent = `${text} / ${shortId}`;
}

function modeLabel(body) {
  if (body.status === "session_timeout") return "Session timeout";
  if (body.status === "service_error") return "Service error";
  if (body.status === "no_result") return "No result";
  if (body.mode === "faq") return "FAQ";
  if (body.mode === "ai") return body.handoff_occurred ? "AI handoff" : "AI";
  if (body.mode === "contact") return "Contact";
  return "Ready";
}

function apiErrorMessage(response, body) {
  if (response.status === 422) return "Invalid request";
  if (typeof body?.detail === "string") return body.detail;
  if (body?.message) return body.message;
  return `HTTP ${response.status}`;
}

function showStatus(message, type) {
  statusBannerEl.textContent = message;
  statusBannerEl.dataset.type = type;
  statusBannerEl.hidden = false;
}

function hideStatus() {
  statusBannerEl.hidden = true;
  statusBannerEl.textContent = "";
  statusBannerEl.removeAttribute("data-type");
}

function scrollToLatest() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function trimTrailingSlash(value) {
  return value.replace(/\/+$/, "");
}

