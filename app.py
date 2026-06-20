import os
import requests
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
SYSTEM_PROMPT = "Sen CiciZeka adında yardımsever, samimi ve akıllı bir yapay zeka asistanısın. Soruları analiz edip en doğru ve faydalı yanıtı ver. Görsel gönderildiğinde onu dikkatle analiz et ve detaylı açıkla. Türkçe konuşmayı tercih et ama kullanıcı hangi dilde yazarsa o dilde cevap ver."


def ask_gemini(messages, image_b64=None, image_mime="image/jpeg"):
    if not API_KEY:
        return "Merhaba! Ben CiciZeka. Şu an demo modundayım, API anahtarı ayarlanmamış."

    try:
        contents = []

        for msg in messages[:-1]:
            contents.append({
                "role": "user" if msg["role"] == "user" else "model",
                "parts": [{"text": msg["content"]}]
            })

        last_parts = []
        if image_b64:
            last_parts.append({"inline_data": {"mime_type": image_mime, "data": image_b64}})
        last_parts.append({"text": messages[-1]["content"] or "Bu görseli analiz et."})

        contents.append({"role": "user", "parts": last_parts})

        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents
        }

        response = requests.post(
            GEMINI_URL,
            headers={"X-goog-api-key": API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        if response.status_code == 429:
            return "Şu an çok yoğunum, birkaç saniye bekleyip tekrar dener misin? 🙏"
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return "Bir sorun oluştu, lütfen tekrar dene."


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

    image_b64 = data.get("image")
    image_mime = data.get("image_mime", "image/jpeg")

    reply = ask_gemini(messages, image_b64, image_mime)
    return jsonify({"reply": reply})


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
