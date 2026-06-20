import os
import json
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

def ask_claude(messages):
    if not API_KEY:
        return mock_response(messages[-1]["content"])

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system="Sen CiciZeka adında yardımsever, samimi ve akıllı bir yapay zeka asistanısın. Türkçe konuşmayı tercih et ama kullanıcı hangi dilde yazarsa o dilde cevap ver.",
            messages=messages,
        )
        return response.content[0].text
    except Exception as e:
        return f"Hata oluştu: {str(e)}"


def mock_response(user_message):
    responses = [
        "Merhaba! Ben CiciZeka. Şu an demo modundayım çünkü API anahtarı ayarlanmamış. Gerçek Claude API'ye bağlanmak için ANTHROPIC_API_KEY ortam değişkenini ayarlayın.",
        "Anlıyorum ne demek istediğinizi. Demo modunda olduğum için gerçek bir yapay zeka yanıtı veremiyorum ama sistem çalışıyor!",
        "Bu çok ilginç bir soru! API anahtarınızı ekledikten sonra size detaylı bir yanıt verebileceğim.",
        "Harika! Sistemin çalıştığını görüyorsunuz. Şimdi sadece ANTHROPIC_API_KEY eklemeniz yeterli.",
    ]
    import random
    return random.choice(responses)


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

    reply = ask_claude(messages)
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
