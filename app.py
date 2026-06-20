import os
import json
import sqlite3
import requests
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
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
def identify_product(image_b64, image_mime):
    if not API_KEY or not image_b64:
        return None
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": image_mime, "data": image_b64}},
                {"text": "Bu görseldeki ürünü tanımla. Sadece ürün adını ve markasını yaz, başka hiçbir şey yazma. Örnek: 'Sony WH-1000XM5 Kulaklık' veya 'Nike Air Max 90 Spor Ayakkabı' veya 'Samsung 65 inç QLED TV'."}
            ]
        }]
    }
    try:
        r = requests.post(
            GEMINI_URL,
            headers={"X-goog-api-key": API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        r.raise_for_status()
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

        response = requests.post(
            GEMINI_URL,
            headers={"X-goog-api-key": API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        if response.status_code == 429:
            return "Şu an çok yoğunum, birkaç saniye bekleyip tekrar dener misin? 🙏", "nötr", []
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
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            parsed = json.loads(raw)
            reply = parsed.get("reply", raw)
            emotion = parsed.get("emotion", "nötr")
            learned = parsed.get("learn", [])
            if learned:
                save_memories(session_id, learned)
            return reply, emotion, learned
        except Exception:
            return raw, "nötr", []
    except Exception:
        return "Bir sorun oluştu, lütfen tekrar dene.", "nötr", []


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
    return jsonify({
        "api_connected": bool(API_KEY),
        "mode": "live" if API_KEY else "demo"
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug, host="0.0.0.0", port=port)
