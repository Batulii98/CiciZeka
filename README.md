# CiciZeka - AI Chat Uygulaması

Modern, minimalist yapay zeka sohbet uygulaması. Claude API ile çalışır.

## Kurulum

```bash
pip install -r requirements.txt
```

## Web Olarak Çalıştırma

**1. API anahtarı ayarlayın:**
```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-...

# Mac / Linux
export ANTHROPIC_API_KEY=sk-ant-...
```

**2. Sunucuyu başlatın:**
```bash
python app.py
```

**3. Tarayıcıda açın:** `http://localhost:5000`

> API anahtarı olmadan demo modunda çalışır.

## Desktop EXE Oluşturma (Windows)

```bash
build_exe.bat
```

`dist/CiciZeka.exe` dosyası oluşur. Bu dosyayı herhangi bir Windows bilgisayarına kopyalayıp çalıştırabilirsiniz.

## Klasör Yapısı

```
CiciZeka/
├── app.py                  # Flask backend
├── desktop_launcher.py     # Desktop başlatıcı
├── requirements.txt
├── run.bat                 # Hızlı başlatma
├── build_exe.bat           # EXE oluşturma
├── templates/
│   └── index.html          # Ana sayfa
└── static/
    ├── css/style.css       # Stiller
    └── js/chat.js          # Sohbet mantığı
```

## Deploy (Online Yayınlama)

### Render.com ile Deploy (Önerilen - Ücretsiz)

1. [render.com](https://render.com) adresine ücretsiz kayıt ol
2. **New > Web Service** tıkla
3. GitHub repo'nu bağla (önce kodu GitHub'a push et)
4. Ayarlar otomatik gelir (`render.yaml` sayesinde)
5. **Environment Variables** bölümünde `ANTHROPIC_API_KEY` ekle
6. **Deploy** tıkla — birkaç dakika sonra URL hazır

> Alternatif: `render.yaml` dosyası mevcut, repo bağlayınca ayarları otomatik okur.

### Railway ile Deploy

1. [railway.app](https://railway.app) adresine GitHub ile giriş yap
2. **New Project > Deploy from GitHub repo** seç
3. Repo'yu seç, otomatik algılar
4. **Variables** sekmesinden `ANTHROPIC_API_KEY` ekle
5. Deploy başlar, URL otomatik atanır

### Manuel Deploy (VPS / Sunucu)

```bash
git clone <repo-url>
cd CiciZeka
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export FLASK_ENV=production
gunicorn app:app --bind 0.0.0.0:8000
```

## GitHub'a Push Etme

```bash
git add .
git commit -m "deployment dosyaları eklendi"
git push
```

## API Anahtarı Alma

[console.anthropic.com](https://console.anthropic.com) adresinden ücretsiz hesap açıp API anahtarı alabilirsiniz.
