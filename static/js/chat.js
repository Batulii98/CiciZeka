const messagesEl = document.getElementById("messages");
const userInput = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const welcomeScreen = document.getElementById("welcomeScreen");

// Conversation history for multi-turn context
let conversationHistory = [];
let isWaiting = false;

// ── Status check ──
async function checkStatus() {
  try {
    const res = await fetch("/status");
    const data = await res.json();
    const dot = document.querySelector(".status-dot");
    const text = document.getElementById("statusText");
    if (data.mode === "live") {
      dot.className = "status-dot live";
      text.textContent = "Claude API bağlı";
    } else {
      dot.className = "status-dot demo";
      text.textContent = "Demo modu";
    }
  } catch {
    document.getElementById("statusText").textContent = "Bağlantı hatası";
  }
}

// ── Send message ──
async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || isWaiting) return;

  hideWelcome();
  addMessage("user", text);
  conversationHistory.push({ role: "user", content: text });

  userInput.value = "";
  autoResize(userInput);
  setWaiting(true);

  const typingEl = addTyping();

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: conversationHistory }),
    });

    const data = await res.json();
    typingEl.remove();

    if (data.reply) {
      addMessage("ai", data.reply);
      conversationHistory.push({ role: "assistant", content: data.reply });
    } else {
      addMessage("ai", "Üzgünüm, bir hata oluştu. Lütfen tekrar deneyin.");
    }
  } catch (err) {
    typingEl.remove();
    addMessage("ai", "Sunucuya bağlanılamadı. Lütfen uygulamanın çalıştığından emin olun.");
  }

  setWaiting(false);
  scrollToBottom();
}

// ── DOM helpers ──
function addMessage(role, text) {
  const isUser = role === "user";
  const msg = document.createElement("div");
  msg.className = `message ${isUser ? "user" : "ai"}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = isUser ? "👤" : "🧠";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  msg.appendChild(avatar);
  msg.appendChild(bubble);
  messagesEl.appendChild(msg);
  scrollToBottom();
  return msg;
}

function addTyping() {
  const msg = document.createElement("div");
  msg.className = "message ai";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "🧠";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = `<div class="typing-indicator"><span></span><span></span><span></span></div>`;

  msg.appendChild(avatar);
  msg.appendChild(bubble);
  messagesEl.appendChild(msg);
  scrollToBottom();
  return msg;
}

function hideWelcome() {
  if (welcomeScreen) {
    welcomeScreen.style.display = "none";
  }
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setWaiting(state) {
  isWaiting = state;
  sendBtn.disabled = state;
  userInput.disabled = state;
}

// ── Suggestion buttons ──
function sendSuggestion(text) {
  userInput.value = text;
  sendMessage();
}

// ── New chat ──
function newChat() {
  conversationHistory = [];
  messagesEl.innerHTML = `
    <div class="welcome-screen" id="welcomeScreen">
      <div class="welcome-icon">🧠</div>
      <h1>Merhaba! Ben CiciZeka</h1>
      <p>Size nasıl yardımcı olabilirim?</p>
      <div class="suggestion-grid">
        <button class="suggestion-btn" onclick="sendSuggestion('Kendini tanıt')">Kendini tanıt</button>
        <button class="suggestion-btn" onclick="sendSuggestion('Bugün nasılsın?')">Bugün nasılsın?</button>
        <button class="suggestion-btn" onclick="sendSuggestion('Bana bir şeyler öğret')">Bana bir şeyler öğret</button>
        <button class="suggestion-btn" onclick="sendSuggestion('Neler yapabilirsin?')">Neler yapabilirsin?</button>
      </div>
    </div>
  `;
}

// ── Keyboard ──
function handleKey(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

// ── Init ──
checkStatus();
