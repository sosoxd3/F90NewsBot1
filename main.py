import feedparser
import requests
import time
import re
from html import unescape
import os
import threading
from flask import Flask

BOT_TOKEN = os.getenv("BOT_TOKEN", "8340084044:AAH4xDclN0yKECmpTFcnL5eshA4-qREHw4w")
CHAT_ID = os.getenv("CHAT_ID", "@f90newsnow")

SOURCES = [
    "https://www.aljazeera.net/xml/rss/all.xml",
    "https://www.skynewsarabia.com/web/rss",
    "https://arabic.rt.com/rss/",
    "https://www.alarabiya.net/.mrss/ar.xml",
    "https://www.bbc.com/arabic/index.xml",
    "https://www.asharqnews.com/ar/rss.xml",
    "https://shehabnews.com/ar/rss.xml",
    "https://qudsn.co/feed",
    "https://maannews.net/rss/ar.xml"
]

FOOTER = (
    "\n\n———\n"
    "📢 انضموا لنا لتَروا الأخبار لحظة بلحظة\n"
    "🌐 موقعنا الرسمي: https://e9dd-009-80041-a80rjkupq6lz-deployed-internal.easysite.ai/\n"
    "📱 تحميل تطبيق الأندرويد: https://newoaks.s3.us-west-1.amazonaws.com/AutoDev/80041/d281064b-a82e-4fdf-bc19-d19cc4e0ccd4.apk\n"
    "📡 تابعنا على تلجرام: https://t.me/f90newsnow"
)

seen = set()

def clean_html(raw):
    raw = unescape(raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = re.sub(r"http\S+", "", raw)  # إزالة الروابط داخل الخبر
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw

def get_full_text(entry):
    if "summary" in entry:
        return clean_html(entry.summary)
    if "description" in entry:
        return clean_html(entry.description)
    return ""

def extract_video(entry):
    """
    يبحث عن روابط فيديو داخل (media_content, enclosures)
    ويدعم MP4 مباشرة.
    """
    for key in ("media_content", "enclosures"):
        if key in entry:
            items = entry[key] if isinstance(entry[key], list) else [entry[key]]
            for i in items:
                url = i.get("url") or i.get("href")
                if url and url.endswith(".mp4"):
                    return url

    # محاولة التقاط فيديو من النص
    if "summary" in entry:
        links = re.findall(r'(https?://\S+)', entry.summary)
        for l in links:
            if l.endswith(".mp4"):
                return l

    return None

def get_image(entry):
    for key in ("media_content", "media_thumbnail", "enclosures"):
        if key in entry:
            try:
                data = entry[key][0] if isinstance(entry[key], list) else entry[key]
                url = data.get("url") or data.get("href")
                if url and url.startswith("http") and not url.endswith(".mp4"):
                    return url
            except:
                pass
    return None

def send_news(title, source, details, img=None, video=None):
    caption = (
        f"🔴 <b>{title}</b>\n\n"
        f"📄 <b>التفاصيل:</b>\n{details}\n\n"
        f"📰 <i>{source}</i>"
        f"{FOOTER}"
    )

    # 🎥 الفيديو أولاً إذا وُجد
    if video:
        try:
            vdata = requests.get(video, timeout=15).content
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
                data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                files={"video": vdata}
            )
            return
        except:
            pass

    # 🖼️ إذا لم يوجد فيديو → نشر الصورة
    if img:
        try:
            idata = requests.get(img, timeout=10).content
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                files={"photo": idata}
            )
            return
        except:
            pass

    # 📝 إرسال نص فقط إن لم يوجد فيديو ولا صورة
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
    )

def run_bot():
    print("🚀 F90 News Bot يعمل الآن…")
    while True:
        new = 0
        for url in SOURCES:
            try:
                feed = feedparser.parse(url)
                source = feed.feed.get("title", "مصدر إخباري")

                for entry in reversed(feed.entries):
                    link = entry.get("link")
                    if not link or link in seen:
                        continue
                    seen.add(link)

                    title = clean_html(entry.get("title", "خبر عاجل"))
                    details = get_full_text(entry)
                    if len(details) < 20:
                        continue

                    img = get_image(entry)
                    video = extract_video(entry)

                    send_news(title, source, details, img, video)
                    new += 1
                    time.sleep(1)

            except Exception as e:
                print("⚠️ ERROR:", e)

        if new == 0:
            print("⏸️ لا أخبار جديدة")
        time.sleep(60)

app = Flask(__name__)

@app.route("/")
def home():
    return "⚡ F90 News Bot يعمل الآن 24/7 دون توقف!"

def run_server():
    app.run("0.0.0.0", 8080)

if __name__ == "__main__":
    threading.Thread(target=run_server).start()
    run_bot()
