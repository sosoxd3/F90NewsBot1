import feedparser
import requests
import time
import re
from html import unescape
import os
import threading
from flask import Flask

# 🔥 مفاتيح البوت
BOT_TOKEN = os.getenv("BOT_TOKEN", "8340084044:AAH4xDclN0yKECmpTFcnL5eshA4-qREHw4w")
CHAT_ID = os.getenv("CHAT_ID", "@f90newsnow")

# 🌍 جميع المصادر (محلية + عربية + عالمية + عبرية)
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
    "https://www.ynetnews.com/category/3082",       # عبرية
    "https://www.israelhayom.co.il/rss.xml",       # عبرية
]

# 🌐 الروابط المخفية الثابتة
FOOTER = (
    "\n\n____________________\n"
    "🛰️ <b>المصدر.</b>\n"
    "🔗 <a href='{SOURCE}'>رابط الخبر</a>\n"
    "____________________\n"
    "🔔 انضموا لنا لقراءة الأخبار لحظة بلحظة\n"
    f"🌐 <a href='https://e9dd-009-80041-a80rjkupq6lz-deployed-internal.easysite.ai/'>موقعنا الرسمي</a>\n"
    f"📱 <a href='https://newoaks.s3.us-west-1.amazonaws.com/AutoDev/80041/d281064b-a82e-4fdf-bc19-d19cc4e0ccd4.apk'>تحميل تطبيق الأندرويد</a>\n"
    f"📡 <a href='https://t.me/f90newsnow'>تابعنا على تلجرام</a>"
)

# 🛑 منع التكرار
seen = set()

# 🧹 تنظيف النص
def clean_text(s):
    s = unescape(s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# 🖼️ الحصول على الصورة
def get_image(entry):
    try:
        if "media_content" in entry:
            return entry.media_content[0]["url"]
        if "media_thumbnail" in entry:
            return entry.media_thumbnail[0]["url"]
    except:
        pass

    if "summary" in entry:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.summary)
        if m:
            return m.group(1)

    return None

# 🎥 الحصول على فيديو إن وجد
def get_video(entry):
    if "links" in entry:
        for link in entry.links:
            if "video" in link.get("type", ""):
                return link.href
    return None

# ✉️ إرسال رسالة
def send_post(title, text, source, link, img=None, video=None):
    caption = f"🔴 <b>{title}</b>\n\n{text}"

    footer = FOOTER.replace("{SOURCE}", link)

    if video:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption + footer,
                    "parse_mode": "HTML"
                },
                files={"video": requests.get(video).content}
            )
            return
        except:
            pass

    if img:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption + footer,
                    "parse_mode": "HTML"
                },
                files={"photo": requests.get(img).content}
            )
            return
        except:
            pass

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": caption + footer, "parse_mode": "HTML"}
    )


# 🚀 تشغيل البوت
def run_bot():
    print("🚀 F90 News Bot يعمل الآن…")

    while True:
        new_news = 0

        for url in SOURCES:
            try:
                feed = feedparser.parse(url)
                source_title = feed.feed.get("title", "مصدر إخباري")

                for entry in reversed(feed.entries):
                    link = entry.get("link")
                    if not link or link in seen:
                        continue

                    seen.add(link)

                    title = clean_text(entry.get("title", ""))
                    text = clean_text(entry.get("summary", ""))

                    img = get_image(entry)
                    video = get_video(entry)

                    send_post(title, text, source_title, link, img, video)
                    new_news += 1
                    time.sleep(2)

            except Exception as e:
                print("⚠️ خطأ:", e)

        if new_news == 0:
            print("⏸️ لا أخبار جديدة – فحص جديد بعد 60 ثانية")

        time.sleep(60)

# 🌐 Flask لمنع إيقاف الخدمة
app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 F90 News Bot يعمل الآن 24/7 بدون توقف!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()
