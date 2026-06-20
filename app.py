import os
import re
import json
import sqlite3
import time
import threading
from collections import deque
import requests
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
IMAGE_GEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-preview-image-generation:generateContent"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL = "llama-3.2-90b-vision-preview"
DB_PATH = Path(__file__).parent / "memory.db"


# ── Database ──
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                fact TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, fact)
            )
        """)
        conn.commit()

init_db()

def get_memories(session_id):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT fact FROM memories WHERE session_id = ? ORDER BY created_at DESC LIMIT 25",
            (session_id,)
        ).fetchall()
    return [r[0] for r in rows]

def save_memories(session_id, facts):
    if not facts:
        return
    with sqlite3.connect(DB_PATH) as conn:
        for fact in facts:
            if fact and fact.strip():
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO memories (session_id, fact) VALUES (?, ?)",
                        (session_id, fact.strip())
                    )
                except Exception:
                    pass
        conn.commit()

def clear_memories(session_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM memories WHERE session_id = ?", (session_id,))
        conn.commit()


# ── Web Search ──
def web_search(query, max_results=4):
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, region="tr-tr"))
        return "\n".join(f"- {r['title']}: {r['body']}" for r in results) if results else ""
    except Exception:
        return ""

def needs_search(text):
    keywords = ["bugün", "şu an", "şimdi", "güncel", "haber", "son dakika",
                "fiyat", "kur", "dolar", "euro", "hava durumu", "ne zaman",
                "vizyonda", "maç", "skor", "borsa", "kripto"]
    return any(k in text.lower() for k in keywords)


# ── Product Search ──
# ── Rate limiter: max 10 req/min to stay under Gemini's 15 RPM ──
_req_times = deque()
_rate_lock = threading.Lock()

def _rate_limit():
    with _rate_lock:
        now = time.time()
        while _req_times and now - _req_times[0] > 60:
            _req_times.popleft()
        if len(_req_times) >= 10:
            wait = 61 - (now - _req_times[0])
            if wait > 0:
                time.sleep(wait)
            now = time.time()
            while _req_times and now - _req_times[0] > 60:
                _req_times.popleft()
        _req_times.append(time.time())

def gemini_post(payload, timeout=30, retries=2):
    _rate_limit()
    for attempt in range(retries + 1):
        r = requests.post(
            GEMINI_URL,
            headers={"X-goog-api-key": API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=timeout
        )
        if r.status_code == 429:
            if attempt < retries:
                time.sleep(20)
                continue
        return r
    return r

def identify_product(image_b64, image_mime):
    if not API_KEY or not image_b64:
        return None
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": image_mime, "data": image_b64}},
                {"text": "Bu görseldeki ürünü tanımla. Sadece ürün adını ve markasını yaz, başka hiçbir şey yazma. Örnek: 'Sony WH-1000XM5 Kulaklık' veya 'Nike Air Max 90 Spor Ayakkabı'."}
            ]
        }]
    }
    try:
        r = gemini_post(payload, timeout=15, retries=1)
        if r.status_code != 200:
            return None
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None

def search_product_links(product_name, max_results=5):
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(
                f"{product_name} satın al trendyol hepsiburada amazon",
                max_results=max_results, region="tr-tr"
            ))
        links = []
        for r in results:
            url = r.get("href", "")
            title = r.get("title", "")
            if url:
                links.append({"title": title, "url": url})
        return links
    except Exception:
        return []

def needs_image_generation(text):
    keywords = ["çiz", "resim yap", "resim çiz", "görsel oluştur", "görsel yap",
                "fotoğraf oluştur", "fotoğraf yap", "illüstrasyon yap", "bana çiz",
                "resim oluştur", "draw me", "generate image", "create image", "paint me"]
    tl = text.lower()
    return any(k in tl for k in keywords)

def generate_image(prompt):
    import base64, urllib.parse
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=768&nologo=true&seed={int(time.time())}"
    try:
        r = requests.get(url, timeout=60)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            mime = r.headers.get("content-type", "image/jpeg").split(";")[0]
            return base64.b64encode(r.content).decode("utf-8"), mime
    except Exception:
        pass
    return None, None

def is_product_query(text):
    keywords = ["link", "nereden", "satın al", "nerede bulunur",
                "sipariş ver", "nereden alabilir", "fiyatı ne", "satıyor mu"]
    return any(k in text.lower() for k in keywords)


# ── Prompts ──
BASE_PROMPT = """Sen CiciZeka adında akıllı ve güvenilir bir yapay zeka asistanısın.

Kişilik:
- Samimi ama profesyonelsin. Doğal bir ton kullanırsın; ne aşırı resmi ne de çocukça.
- Net ve öz konuşursun. Doğrudan konuya girersin.
- Emoji kullanabilirsin ama ölçülü — her cümlede değil, anlam kattığında.
- Eğlenceli sorularda hafif mizah yapabilirsin.
- Kullanıcının ruh haline göre empati gösterir, tonunu ayarlarsın.
- Kullanıcı hakkında öğrendiğin bilgileri doğal biçimde konuşmaya yansıt; "kayıtlarda var" diye söyleme.

Görev:
- Soruları dikkatle analiz et ve en doğru, faydalı yanıtı ver.
- Görsel gönderildiğinde onu detaylı ve açık biçimde analiz et.
- Görsel bir ürüne aitse ve satın alma linkleri verilmişse, bu linkleri yanıtında mutlaka paylaş. Linkleri tam URL olarak yaz.
- Türkçe konuşmayı tercih et; kullanıcı hangi dilde yazarsa o dilde yanıt ver.

ÇIKTI FORMATI — Yanıtını SADECE aşağıdaki JSON formatında döndür:
{
  "reply": "<yanıt metni>",
  "emotion": "<mutlu|üzgün|kızgın|endişeli|yorgun|heyecanlı|nötr>",
  "learn": ["<öğrenilecek kişisel bilgi>"]
}
"learn": Kullanıcı hakkında öğrenebileceğin bilgileri ekle (isim, meslek, hobiler, tercihler vb.). Yoksa []."""


def build_prompt(memories):
    if not memories:
        return BASE_PROMPT
    mem_text = "\n".join(f"  - {m}" for m in memories)
    return BASE_PROMPT + f"\n\nBu kullanıcı hakkında önceki sohbetlerden öğrendiklerin:\n{mem_text}"


# ── LLM response parser ──
def parse_llm_response(raw):
    # Kod bloğunu temizle
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    # Direkt JSON dene
    try:
        parsed = json.loads(cleaned)
        return parsed.get("reply", cleaned), parsed.get("emotion", "nötr"), parsed.get("learn", [])
    except Exception:
        pass

    # Metin içinde JSON bul
    match = re.search(r'\{.*?"reply".*?\}', cleaned, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            return parsed.get("reply", cleaned), parsed.get("emotion", "nötr"), parsed.get("learn", [])
        except Exception:
            pass

    # "reply:" önekini temizle
    for prefix in ["reply:", "Reply:", '"reply":', 'REPLY:']:
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip().strip('"')
            break

    return cleaned, "nötr", []


# ── Groq ──
def ask_groq(messages, session_id, image_b64=None, image_mime="image/jpeg"):
    if not GROQ_API_KEY:
        return None, "nötr", []

    memories = get_memories(session_id)
    system_prompt = build_prompt(memories)

    groq_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages[:-1]:
        role = "user" if msg["role"] == "user" else "assistant"
        groq_messages.append({"role": role, "content": msg["content"]})

    last_text = messages[-1].get("content", "") or "Bu görseli detaylıca analiz et."
    augmented = last_text
    if needs_search(last_text) and not image_b64:
        ctx = web_search(last_text)
        if ctx:
            augmented += f"\n\n[Güncel internet araması:\n{ctx}]"

    if image_b64:
        last_content = [
            {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}},
            {"type": "text", "text": augmented}
        ]
        model = GROQ_VISION_MODEL
    else:
        last_content = augmented
        model = GROQ_MODEL

    groq_messages.append({"role": "user", "content": last_content})

    payload = {
        "model": model,
        "messages": groq_messages,
        "temperature": 0.7,
        "max_tokens": 1024
    }
    try:
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=45
        )
        if r.status_code != 200:
            return None, "nötr", []
        raw = r.json()["choices"][0]["message"]["content"].strip()
        reply, emotion, learned = parse_llm_response(raw)
        if learned:
            save_memories(session_id, learned)
        return reply, emotion, learned
    except Exception:
        return None, "nötr", []


# ── Gemini ──
def ask_gemini(messages, session_id, image_b64=None, image_mime="image/jpeg"):
    if not API_KEY:
        return "Demo modundayım, API anahtarı yok.", "nötr", []

    memories = get_memories(session_id)
    system_prompt = build_prompt(memories)

    try:
        contents = []
        for msg in messages[:-1]:
            contents.append({
                "role": "user" if msg["role"] == "user" else "model",
                "parts": [{"text": msg["content"]}]
            })

        last_text = messages[-1]["content"] or "Bu görseli analiz et."
        search_context = ""
        if needs_search(last_text):
            search_context = web_search(last_text)

        # Product link search: only when image + user asks for link/buying info
        product_context = ""
        if image_b64 and is_product_query(last_text):
            product_name = identify_product(image_b64, image_mime)
            if product_name:
                links = search_product_links(product_name)
                if links:
                    product_context = f"\n\n[Ürün: {product_name} — satın alma bağlantıları:\n"
                    for lnk in links[:4]:
                        product_context += f"- {lnk['title']}: {lnk['url']}\n"
                    product_context += "]"

        last_parts = []
        if image_b64:
            last_parts.append({"inline_data": {"mime_type": image_mime, "data": image_b64}})
        msg_text = last_text
        if search_context:
            msg_text += f"\n\n[Güncel internet araması sonuçları:\n{search_context}]"
        if product_context:
            msg_text += product_context
        last_parts.append({"text": msg_text})
        contents.append({"role": "user", "parts": last_parts})

        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents
        }

        response = gemini_post(payload, timeout=30, retries=2)
        if response.status_code == 429:
            return "API istek limitine ulaşıldı. 1 dakika bekleyip tekrar dener misin?", "nötr", []
        response.raise_for_status()

        resp_json = response.json()

        # Gemini may block the response (safety filter)
        candidates = resp_json.get("candidates", [])
        if not candidates:
            return "Bu konuda sana yardımcı olamadım, farklı bir şekilde sormayı dene.", "nötr", []

        finish_reason = candidates[0].get("finishReason", "")
        if finish_reason in ("SAFETY", "RECITATION", "BLOCKED"):
            return "Bu içerik için yanıt oluşturamadım. Farklı bir şekilde sorabilirsin.", "nötr", []

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return "Bir sorun oluştu, lütfen tekrar dene.", "nötr", []

        raw = parts[0]["text"].strip()
        reply, emotion, learned = parse_llm_response(raw)
        if learned:
            save_memories(session_id, learned)
        return reply, emotion, learned
    except Exception as e:
        return f"Bir sorun oluştu: {str(e)[:120]}", "nötr", []


# ── Routes ──
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True, silent=True)
    if not data or "messages" not in data:
        return jsonify({"error": "Geçersiz istek"}), 400
    messages = data["messages"]
    if not messages:
        return jsonify({"error": "Mesaj listesi boş"}), 400

    session_id = data.get("session_id", "default")
    image_b64 = data.get("image")
    image_mime = data.get("image_mime", "image/jpeg")

    last_msg = messages[-1].get("content", "")

    if needs_image_generation(last_msg):
        gen_img, gen_mime = generate_image(last_msg)
        if gen_img:
            return jsonify({
                "reply": "İşte isteğin doğrultusunda oluşturduğum görsel! 🎨",
                "emotion": "heyecanlı",
                "learned": [],
                "generated_image": gen_img,
                "generated_image_mime": gen_mime
            })

    if GROQ_API_KEY:
        reply, emotion, learned = ask_groq(messages, session_id, image_b64, image_mime)
        if reply is not None:
            return jsonify({"reply": reply, "emotion": emotion, "learned": learned})

    reply, emotion, learned = ask_gemini(messages, session_id, image_b64, image_mime)
    return jsonify({"reply": reply, "emotion": emotion, "learned": learned})


@app.route("/memories/<session_id>", methods=["GET"])
def memories_get(session_id):
    return jsonify({"memories": get_memories(session_id)})


@app.route("/memories/<session_id>", methods=["DELETE"])
def memories_delete(session_id):
    clear_memories(session_id)
    return jsonify({"status": "cleared"})


@app.route("/status")
def status():
    if GROQ_API_KEY:
        return jsonify({"api_connected": True, "mode": "groq"})
    elif API_KEY:
        return jsonify({"api_connected": True, "mode": "live"})
    else:
        return jsonify({"api_connected": False, "mode": "demo"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug, host="0.0.0.0", port=port)
