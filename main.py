import feedparser
import requests
import time
import re
from html import unescape
import os
import threading
from datetime import datetime, timedelta
from flask import Flask

# ============================
#   إعدادات البوت
# ============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "TO_BE_SET")
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

# ===== 🔥 إعلان مخفي (لا يظهر كرابط) =====
AD_LINK = '<a href="https://www.effectivegatecpm.com/y7ytegiy?key=8987b0a0eccadab53fa69732c3e254b8">🎥 شاهد</a>'

# نص الحقوق
FOOTER = (
    "\n———\n"
    f"📺 {AD_LINK} (بث مباشر)\n\n"
    "📢 انضموا لنا لتَروا الأخبار لحظة بلحظة\n"
    "🌐 موقعنا الرسمي: https://e9dd-009-80041-a80rjkupq6lz-deployed-internal.easysite.ai/\n"
    "📱 تحميل تطبيق الأندرويد: https://newoaks.s3.us-west-1.amazonaws.com/AutoDev/80041/d281064b-a82e-4fdf-bc19-d19cc4e0ccd4.apk\n"
    "📡 تابعنا على تلجرام: https://t.me/f90newsnow"
)

seen_links = set()
seen_titles = set()
SEEN_LIMIT = 5000

# ============================
#   دوال مساعدة
# ============================

def clean_html(raw: str) -> str:
    if not raw:
        return ""
    raw = unescape(raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"http\S+", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw

def get_full_text(entry) -> str:
    if "summary" in entry:
        return clean_html(entry.summary)
    if "description" in entry:
        return clean_html(entry.description)
    return ""

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
    summary = getattr(entry, "summary", "")
    m = re.search(r'<img[^>]+src="([^"]+)"', summary)
    if m:
        return m.group(1)
    return None

def get_video(entry):
    summary = getattr(entry, "summary", "")
    links = re.findall(r"(https?://\S+)", summary)
    for l in links:
        if l.endswith(".mp4"):
            return l
    return None

def get_entry_datetime(entry):
    for key in ("published_parsed", "updated_parsed"):
        if key in entry and entry[key]:
            try:
                return datetime(*entry[key][:6])
            except:
                pass
    return None

def is_recent(entry, hours=24):
    d = get_entry_datetime(entry)
    if not d:
        return False
    return (datetime.utcnow() - d) <= timedelta(hours=hours)

# ============================
#   الإرسال
# ============================

def send_news(title, source, details, img=None, vid=None):
    caption = (
        f"🔴 <b>{title}</b>\n\n"
        f"📄 <b>التفاصيل:</b>\n{details}\n\n"
        f"📰 <i>{source}</i>"
        f"{FOOTER}"
    )

    # فيديو
    if vid:
        try:
            vdata = requests.get(vid, timeout=15).content
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
                data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                files={"video": vdata}
            )
            return
        except:
            pass

    # صورة
    if img:
        try:
            pdata = requests.get(img, timeout=15).content
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                files={"photo": pdata}
            )
            return
        except:
            pass

    # نص فقط
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
    )

# ============================
#   حلقة تشغيل الأخبار
# ============================

def run_bot():
    print("🚀 Bot F90 News يعمل الآن…")
    while True:
        new_count = 0

        for url in SOURCES:
            try:
                feed = feedparser.parse(url)
                source = feed.feed.get("title", "مصدر إخباري")

                for entry in reversed(feed.entries):
                    if not is_recent(entry):
                        continue

                    link = entry.get("link", "")
                    if not link or link in seen_links:
                        continue

                    title = clean_html(entry.get("title", "خبر عاجل"))
                    if title.lower() in seen_titles:
                        continue

                    details = get_full_text(entry)
                    if len(details) < 30:
                        continue

                    img = get_image(entry)
                    vid = get_video(entry)

                    send_news(title, source, details, img, vid)

                    seen_links.add(link)
                    seen_titles.add(title.lower())
                    new_count += 1
                    time.sleep(2)

            except Exception as e:
                print("⚠️ خطأ:", e)

        if new_count == 0:
            print("⏸ لا أخبار جديدة…")

        time.sleep(60)

# ============================
# Flask
# ============================

app = Flask(__name__)

@app.route("/")
def home():
    return "F90 News Bot يعمل الآن ✔✔"

@app.route("/test")
def test():
    test_msg = f"🔴 <b>رسالة اختبار</b>\n\nالبوت يعمل بنجاح\n{FOOTER}"
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": test_msg, "parse_mode": "HTML"}
    )
    return "تم إرسال رسالة اختبار."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()
