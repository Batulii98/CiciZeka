import os
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("GEMINI_API_KEY", "")


def ask_gemini(messages):
    if not API_KEY:
        return mock_response(messages[-1]["content"])

    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction="Sen CiciZeka adında yardımsever, samimi ve akıllı bir yapay zeka asistanısın. Soruları analiz edip en doğru ve faydalı yanıtı ver. Türkçe konuşmayı tercih et ama kullanıcı hangi dilde yazarsa o dilde cevap ver."
        )
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        chat = model.start_chat(history=history)
        response = chat.send_message(messages[-1]["content"])
        return response.text
    except Exception as e:
        return f"Hata oluştu: {str(e)}"


def mock_response(user_message):
    return "Merhaba! Ben CiciZeka. Şu an demo modundayım, API anahtarı ayarlanmamış."


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
