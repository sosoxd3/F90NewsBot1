import feedparser
import requests
import time
import re
from html import unescape
import os
import threading
from flask import Flask
from deep_translator import GoogleTranslator

# -----------------------------
# إعدادات البوت
# -----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "ضع-توكن-البوت-هنا")
CHAT_ID = os.getenv("CHAT_ID", "@f90newsnow")

# -----------------------------
# روابط المستخدم
# -----------------------------
SITE_URL = "https://e9dd-009-80041-a80rjkupq6lz-deployed-internal.easysite.ai/"
APP_URL  = "https://newoaks.s3.us-west-1.amazonaws.com/AutoDev/80041/d281064b-a82e-4fdf-bc19-d19cc4e0ccd4.apk"
TG_URL   = "https://t.me/f90newsnow"

# -----------------------------
# مصادر الأخبار
# -----------------------------
SOURCES = [
    "https://www.aljazeera.net/xml/rss/all.xml",
    "https://www.skynewsarabia.com/web/rss",
    "https://arabic.rt.com/rss/",
    "https://www.alarabiya.net/.mrss/ar.xml",
    "https://www.bbc.com/arabic/index.xml",
    "https://www.asharqnews.com/ar/rss.xml",
    "https://shehabnews.com/ar/rss.xml",
    "https://qudsn.co/feed",
    "https://maannews.net/rss/ar.xml",
    # مصادر عبرية + إنجليزية (ترجمة تلقائية)
    "https://www.timesofisrael.com/feed/",
    "https://www.jpost.com/Rss/RssFeedsHeadlines.aspx",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
]

seen = set()

# -----------------------------
# تنظيف النص
# -----------------------------
def clean_text(s):
    s = unescape(s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# -----------------------------
# كشف اللغة وترجمتها
# -----------------------------
def translate_if_needed(text):
    hebrew = re.search(r"[\u0590-\u05FF]", text)
    english = re.search(r"[A-Za-z]", text)

    if hebrew or english:
        try:
            return GoogleTranslator(source='auto', target='ar').translate(text)
        except:
            return text
    return text

# -----------------------------
# جلب الصورة / الفيديو
# -----------------------------
def get_media(entry):
    # صورة
    if "media_content" in entry:
        try:
            item = entry["media_content"][0]
            if "url" in item:
                return item["url"]
        except:
            pass

    # صورة داخل الملخص
    if "summary" in entry:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry["summary"])
        if m:
            return m.group(1)

    return None

# -----------------------------
# إرسال الخبر
# -----------------------------
def send_post(title, body, source, link, media):
    # --- ترجمة إذا لزم ---
    title = translate_if_needed(title)
    body  = translate_if_needed(body)

    # --- الرسالة النهائية ---
    msg = (
        f"🔴 <b>{title}</b>\n\n"
        f"{body}\n\n"
        f"____________________\n"
        f"📡 <b>المصدر:</b> {source}\n"
        f"<a href='{link}'>📎 رابط الخبر</a>\n"
        f"____________________\n"
        f"🔔 انضموا لنا لقراءة الأخبار لحظة بلحظة\n"
        f"<a href='{SITE_URL}'>🌐 موقعنا الرسمي</a>\n"
        f"<a href='{APP_URL}'>📱 تحميل تطبيق الأندرويد</a>\n"
        f"<a href='{TG_URL}'>📡 تابعنا على تلجرام</a>"
    )

    # --- إرسال صورة أو فيديو ---
    if media:
        try:
            data = requests.get(media, timeout=10).content
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={"chat_id": CHAT_ID, "caption": msg, "parse_mode": "HTML"},
                files={"photo": data},
            )
            return
        except:
            pass

    # إرسال نص فقط
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
    )

# -----------------------------
# تشغيل البوت
# -----------------------------
def run_bot():
    print("🚀 Bot Started…")
    while True:
        new_posts = 0

        for url in SOURCES:
            try:
                feed = feedparser.parse(url)
                source = feed.feed.get("title", "مصدر إخباري")

                for entry in feed.entries:
                    link = entry.get("link")
                    if not link or link in seen:
                        continue

                    seen.add(link)

                    title = clean_text(entry.get("title", ""))
                    body  = clean_text(entry.get("summary", ""))

                    media = get_media(entry)

                    send_post(title, body, source, link, media)

                    new_posts += 1
                    time.sleep(1)

            except Exception as e:
                print("❌ Error:", e)

        if new_posts == 0:
            print("⏸️ لا أخبار جديدة…")

        time.sleep(60)

# -----------------------------
# Flask لابقاء Render شغال
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "F90 News Bot Running 24/7"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# -----------------------------
# تشغيل الخوادم
# -----------------------------
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()
