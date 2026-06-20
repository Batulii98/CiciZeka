const messagesEl = document.getElementById("messages");
const userInput = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const welcomeScreen = document.getElementById("welcomeScreen");

let conversationHistory = [];
let isWaiting = false;
let currentChatId = crypto.randomUUID();
let memoryVisible = true;

// ── Session & Memory ──
const SESSION_ID = localStorage.getItem("cz_session") || (() => {
  const id = crypto.randomUUID();
  localStorage.setItem("cz_session", id);
  return id;
})();

async function loadMemories() {
  try {
    const res = await fetch(`/memories/${SESSION_ID}`);
    const data = await res.json();
    renderMemories(data.memories || []);
  } catch {}
}

function renderMemories(memories) {
  const list = document.getElementById("memoryList");
  if (!memories.length) {
    list.innerHTML = '<p class="memory-empty">Henüz bir şey öğrenmedim.</p>';
    return;
  }
  list.innerHTML = memories.map(m => `<div class="memory-item">${m}</div>`).join("");
}

async function clearMemory() {
  showConfirm("Tüm hafıza silinecek. Emin misin?", async () => {
    await fetch(`/memories/${SESSION_ID}`, { method: "DELETE" });
    renderMemories([]);
  });
}

function toggleMemory() {
  memoryVisible = !memoryVisible;
  document.getElementById("memoryList").style.display = memoryVisible ? "" : "none";
  document.getElementById("memoryToggle").textContent = memoryVisible ? "▲" : "▼";
}

// ── Confirm dialog ──
let _confirmCb = null;

function showConfirm(text, onYes) {
  document.getElementById("confirmText").textContent = text;
  document.getElementById("confirmModal").style.display = "flex";
  _confirmCb = onYes;
}

function confirmYes() {
  document.getElementById("confirmModal").style.display = "none";
  if (_confirmCb) _confirmCb();
  _confirmCb = null;
}

function confirmNo() {
  document.getElementById("confirmModal").style.display = "none";
  _confirmCb = null;
}

// ── Chat History ──
const HISTORY_KEY = "cz_chat_history";

function getChatHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); }
  catch { return []; }
}

function saveCurrentChat() {
  if (!conversationHistory.length) return;
  const history = getChatHistory();
  const title = conversationHistory[0]?.content?.slice(0, 36) || "Sohbet";
  const chat = { id: currentChatId, title, messages: [...conversationHistory], ts: Date.now() };
  const idx = history.findIndex(c => c.id === currentChatId);
  if (idx >= 0) history[idx] = chat; else history.unshift(chat);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 30)));
  renderChatHistory();
}

function renderChatHistory() {
  const list = document.getElementById("chatHistoryList");
  if (!list) return;
  const history = getChatHistory();
  if (!history.length) {
    list.innerHTML = '<p class="memory-empty">Henüz sohbet yok.</p>';
    return;
  }
  list.innerHTML = history.map(c => `
    <div class="chat-history-item${c.id === currentChatId ? " active" : ""}" onclick="loadChat('${c.id}')">
      <span class="chat-history-title">${c.title}</span>
      <button class="chat-delete-btn" onclick="deleteChatItem(event,'${c.id}')" title="Sil">✕</button>
    </div>
  `).join("");
}

function loadChat(id) {
  if (id === currentChatId) return;
  saveCurrentChat();
  const chat = getChatHistory().find(c => c.id === id);
  if (!chat) return;
  currentChatId = id;
  conversationHistory = [...chat.messages];
  messagesEl.innerHTML = "";
  if (welcomeScreen) welcomeScreen.style.display = "none";
  for (const msg of conversationHistory) {
    addMessage(msg.role === "user" ? "user" : "ai", msg.content);
  }
  renderChatHistory();
}

function deleteChatItem(e, id) {
  e.stopPropagation();
  const history = getChatHistory().filter(c => c.id !== id);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  if (id === currentChatId) startNewChat();
  else renderChatHistory();
}

// ── Image state ──
let pendingImage = null;
let pendingImageMime = "image/jpeg";

function handleImageSelect(e) {
  const file = e.target.files[0];
  if (!file) return;
  pendingImageMime = file.type || "image/jpeg";
  const reader = new FileReader();
  reader.onload = (ev) => {
    pendingImage = ev.target.result.split(",")[1];
    document.getElementById("previewImg").src = ev.target.result;
    document.getElementById("imagePreview").style.display = "flex";
  };
  reader.readAsDataURL(file);
  e.target.value = "";
}

function removeImage() {
  pendingImage = null;
  document.getElementById("imagePreview").style.display = "none";
  document.getElementById("previewImg").src = "";
}

// ── Voice state ──
let isRecording = false;
let voiceEnabled = false;
let recognition = null;

function initSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;
  recognition = new SR();
  recognition.lang = "tr-TR";
  recognition.interimResults = false;
  recognition.continuous = false;
  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript;
    userInput.value = text;
    autoResize(userInput);
    stopRecording();
    sendMessage();
  };
  recognition.onerror = () => stopRecording();
  recognition.onend = () => stopRecording();
  return true;
}

function toggleMic() {
  if (!recognition && !initSpeech()) {
    alert("Tarayıcınız mikrofonu desteklemiyor. Chrome veya Edge kullanın.");
    return;
  }
  isRecording ? stopRecording() : startRecording();
}

function startRecording() {
  try { recognition.start(); } catch(e) { return; }
  isRecording = true;
  document.getElementById("micBtn").classList.add("recording");
  userInput.placeholder = "🎙️ Dinliyorum...";
}

function stopRecording() {
  try { recognition && recognition.stop(); } catch(e) {}
  isRecording = false;
  const btn = document.getElementById("micBtn");
  if (btn) btn.classList.remove("recording");
  userInput.placeholder = "Bir şeyler yazın... (Enter ile gönderin, Shift+Enter ile satır ekleyin)";
}

function toggleVoice() {
  voiceEnabled = !voiceEnabled;
  const btn = document.getElementById("voiceToggle");
  btn.classList.toggle("active", voiceEnabled);
  btn.title = voiceEnabled ? "Sesli yanıt: Açık" : "Sesli yanıt: Kapalı";
}

function speak(text) {
  if (!voiceEnabled || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "tr-TR";
  u.rate = 1.0;
  u.pitch = 1.1;
  window.speechSynthesis.speak(u);
}

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
  addMessage("user", text, pendingImage ? `data:${pendingImageMime};base64,${pendingImage}` : null);
  conversationHistory.push({ role: "user", content: text });

  const imageToSend = pendingImage;
  const mimeToSend = pendingImageMime;
  removeImage();

  userInput.value = "";
  autoResize(userInput);
  setWaiting(true);

  const typingEl = addTyping();

  try {
    const body = { messages: conversationHistory, session_id: SESSION_ID };
    if (imageToSend) { body.image = imageToSend; body.image_mime = mimeToSend; }

    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await res.json();
    typingEl.remove();

    if (data.reply) {
      addMessage("ai", data.reply, null, data.emotion);
      conversationHistory.push({ role: "assistant", content: data.reply });
      setAvatarState("talking");
      speak(data.reply);
      setTimeout(() => setAvatarState("idle"), Math.min(data.reply.length * 60, 8000));
      if (data.learned && data.learned.length) loadMemories();
      saveCurrentChat();
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
const EMOTION_LABELS = {
  mutlu: "😊 Mutlu", üzgün: "😔 Üzgün", kızgın: "😠 Kızgın",
  endişeli: "😰 Endişeli", yorgun: "😴 Yorgun", heyecanlı: "🤩 Heyecanlı", nötr: "nötr"
};

function addMessage(role, text, imageSrc = null, emotion = null) {
  const isUser = role === "user";
  const msg = document.createElement("div");
  msg.className = `message ${isUser ? "user" : "ai"}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = isUser ? "👤" : "🧠";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (imageSrc) {
    const img = document.createElement("img");
    img.src = imageSrc;
    img.alt = "Yüklenen görsel";
    bubble.appendChild(img);
  }

  const textNode = document.createElement("span");
  textNode.innerHTML = linkify(text);
  bubble.appendChild(textNode);

  if (emotion && emotion !== "nötr" && role === "ai") {
    const tag = document.createElement("div");
    tag.className = `emotion-tag ${emotion}`;
    tag.textContent = EMOTION_LABELS[emotion] || emotion;
    bubble.appendChild(tag);
  }

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
  setAvatarState(state ? "thinking" : "idle");
}

// ── Avatar ──
function setAvatarState(state) {
  const avatar = document.getElementById("czAvatar");
  const status = document.getElementById("avatarStatus");
  if (!avatar) return;
  avatar.className = "cz-avatar";
  if (state === "thinking") {
    avatar.classList.add("thinking");
    if (status) status.textContent = "Düşünüyor...";
  } else if (state === "talking") {
    avatar.classList.add("talking");
    if (status) status.textContent = "Yanıtlıyor...";
  } else {
    if (status) status.textContent = "Dinliyorum...";
  }
}

// ── Suggestion buttons ──
function sendSuggestion(text) {
  userInput.value = text;
  sendMessage();
}

// ── New chat ──
function newChat() {
  if (!conversationHistory.length) { startNewChat(); return; }
  showConfirm("Yeni sohbet açmak istediğine emin misin?", () => {
    saveCurrentChat();
    startNewChat();
  });
}

function startNewChat() {
  currentChatId = crypto.randomUUID();
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
  renderChatHistory();
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

// ── Linkify ──
function linkify(text) {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped.replace(
    /(https?:\/\/[^\s<>"]+)/g,
    url => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
  );
}

// ── Init ──
checkStatus();
loadMemories();
renderChatHistory();
