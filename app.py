import os
import requests
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
SYSTEM_PROMPT = "Sen CiciZeka adında yardımsever, samimi ve akıllı bir yapay zeka asistanısın. Soruları analiz edip en doğru ve faydalı yanıtı ver. Türkçe konuşmayı tercih et ama kullanıcı hangi dilde yazarsa o dilde cevap ver."


def ask_gemini(messages):
    if not API_KEY:
        return "Merhaba! Ben CiciZeka. Şu an demo modundayım, API anahtarı ayarlanmamış."

    try:
        contents = [{"role": "user" if m["role"] == "user" else "model",
                     "parts": [{"text": m["content"]}]} for m in messages]

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
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Hata oluştu: {str(e)}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data or "messages" not in data:
        return jsonify({"error": "Geçersiz istek"}), 400
    messages = data["messages"]
    if not messages:
        return jsonify({"error": "Mesaj listesi boş"}), 400
    reply = ask_gemini(messages)
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
