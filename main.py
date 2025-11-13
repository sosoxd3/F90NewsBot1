import feedparser
import requests
import time
import re
from html import unescape
import os
import threading
from flask import Flask

# ============================
#   إعدادات البوت
# ============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8340084044:AAH4xDclN0yKECmpTFcnL5eshA4-qREHw4w")
CHAT_ID = os.getenv("CHAT_ID", "@f90newsnow")

# ============================
#   مصادر الأخبار (نفس القديم + تحسين)
# ============================

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

# كلمات تعطي أولوية لفلسطين
PALESTINE_KEYWORDS = [
    "غزة","فلسطين","الضفة","القدس","جنين","نابلس","الخليل",
    "شهيد","شهداء","استشهاد","قصف","غارة","صاروخ","صواريخ",
    "توغل","اقتحام","مستوطن","الاحتلال","أسرى","أسير","اعتقال"
]

# نص الروابط الثابتة أسفل كل خبر
FOOTER = (
    "\n———\n"
    "📢 انضموا لنا لتَروا الأخبار لحظة بلحظة\n"
    "🌐 <a href='https://e9dd-009-80041-a80rjkupq6lz-deployed-internal.easysite.ai/'>موقعنا الرسمي</a>\n"
    "📲 <a href='https://newoaks.s3.us-west-1.amazonaws.com/AutoDev/80041/d281064b-a82e-4fdf-bc19-d19cc4e0ccd4.apk'>تحميل تطبيق الأندرويد</a>\n"
    "📡 <a href='https://t.me/f90newsnow'>تابعنا على تلجرام</a>"
)

seen_links = set()
seen_titles = set()
SEEN_LIMIT = 5000

# ============================
#   أدوات مساعدة
# ============================

def clean_html(text):
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def get_image(entry):
    for key in ("media_content","media_thumbnail","enclosures"):
        if key in entry:
            try:
                data = entry[key][0] if isinstance(entry[key],list) else entry[key]
                url = data.get("url") or data.get("href")
                if url and url.startswith("http"):
                    return url
            except:
                pass

    summary = entry.get("summary","") or entry.get("description","")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    if m:
        return m.group(1)

    return None

def is_palestine_news(title, desc):
    text = (title or "") + " " + (desc or "")
    return any(k in text for k in PALESTINE_KEYWORDS)

def summarize_text(text, max_chars=260):
    text = clean_html(text)
    if len(text) <= max_chars:
        return text
    parts = re.split(r"[\.!\؟?!]", text)
    summary = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(summary)+len(p)+2 > max_chars:
            break
        summary += p + ". "
    return summary.strip() or text[:max_chars] + "..."

def shrink_seen():
    global seen_links, seen_titles
    if len(seen_links) > SEEN_LIMIT:
        seen_links = set(list(seen_links)[-2500:])
    if len(seen_titles) > SEEN_LIMIT:
        seen_titles = set(list(seen_titles)[-2500:])

# ============================
#   إرسال الرسائل
# ============================

def send_message(title, description, source, link, img=None, priority=2):

    icon = "🔴" if priority == 1 else "🔵"

    clean_title = clean_html(title)
    clean_desc  = clean_html(description)

    summary = summarize_text(clean_desc)

    text_parts = [
        f"{icon} <b>{clean_title}</b>",
        f"\n📘 <b>ملخص سريع:</b>\n{summary}",
        f"\n📄 <b>التفاصيل:</b>\n{clean_desc}",
        f"\n📡 <i>{source}</i>",
        f"📎 <a href='{link}'>رابط الخبر</a>",
        FOOTER
    ]

    full_text = "\n".join(text_parts)

    if img:
        try:
            photo_data = requests.get(img, timeout=10).content
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={"chat_id": CHAT_ID, "caption": full_text, "parse_mode": "HTML"},
                files={"photo": photo_data}
            )
            return
        except:
            pass

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": full_text, "parse_mode": "HTML"}
    )

# ============================
#   تشغيل البوت 24/7
# ============================

def run_bot():
    print("🚀 Smart F90 News Bot يعمل الآن…")
    while True:
        shrink_seen()
        for url in SOURCES:
            try:
                feed = feedparser.parse(url)
                source = feed.feed.get("title","مصدر خبري")

                for entry in reversed(feed.entries):
                    link = entry.get("link","")
                    title = entry.get("title","")
                    desc  = entry.get("summary","") or entry.get("description","")

                    if not link or not title:
                        continue

                    key_title = clean_html(title).lower()

                    if link in seen_links or key_title in seen_titles:
                        continue

                    seen_links.add(link)
                    seen_titles.add(key_title)

                    img = get_image(entry)
                    priority = 1 if is_palestine_news(title, desc) else 2

                    send_message(title, desc, source, link, img, priority)

                    time.sleep(2 if priority == 1 else 4)

            except Exception as e:
                print("⚠️ خطأ:", e)

        print("⏳ لا جديد… الانتظار 60 ثانية")
        time.sleep(60)


# خادم Flask حتى يبقى البوت شغال على Render
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Smart F90 News Bot مستمر بالعمل 24/7"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# تشغيل Flask + البوت
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()
