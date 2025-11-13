import feedparser
import requests
import time
import re
from html import unescape
import os
import threading
from flask import Flask
from googletrans import Translator  # للترجمة التلقائية

# ================= إعدادات أساسية =================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8340084044:AAH4xDclN0yKECmpTFcnL5eshA4-qREHw4w")
CHAT_ID = os.getenv("CHAT_ID", "@f90newsnow")

SITE_URL = "https://e9dd-009-80041-a80rjkupq6lz-deployed-internal.easysite.ai/"
APP_URL = "https://newoaks.s3.us-west-1.amazonaws.com/AutoDev/80041/d281064b-a82e-4fdf-bc19-d19cc4e0ccd4.apk"
CHANNEL_URL = "https://t.me/f90newsnow"

translator = Translator()

# ================= مصادر الأخبار =================
# الترتيب = أولوية: فلسطين / غزة → عبرية مترجمة → عربية عامة → عالمية

SOURCES = [
    # 🇵🇸 فلسطين / غزة (عربي)
    {"url": "https://shehabnews.com/ar/rss.xml", "lang": "ar"},
    {"url": "https://qudsn.co/feed", "lang": "ar"},
    {"url": "https://maannews.net/rss/ar.xml", "lang": "ar"},
    {"url": "https://www.aljazeera.net/xml/rss/all.xml", "lang": "ar"},

    # 🇮🇱 مصادر عبرية (ستُترجم للعربية)
    {"url": "https://www.ynet.co.il/Integration/StoryRss2.xml", "lang": "he"},
    {"url": "https://rss.walla.co.il/feed/1", "lang": "he"},

    # 🌍 عربية عامة
    {"url": "https://www.skynewsarabia.com/web/rss", "lang": "ar"},
    {"url": "https://arabic.rt.com/rss/", "lang": "ar"},
    {"url": "https://www.alarabiya.net/.mrss/ar.xml", "lang": "ar"},
    {"url": "https://www.bbc.com/arabic/index.xml", "lang": "ar"},
    {"url": "https://www.asharqnews.com/ar/rss.xml", "lang": "ar"},
    {"url": "https://arabic.cnn.com/rss", "lang": "ar"},

    # 🌐 عالمية إنجليزية (ستُترجم)
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "lang": "en"},
]

# =============== نص الروابط المخفية في آخر كل خبر ===============

FOOTER = (
    "\n____________________\n"
    "🔔 انضموا لنا لقراءة الأخبار لحظة بلحظة\n"
    f"🌐 <a href='{SITE_URL}'>موقعنا الرسمي</a> • "
    f"📱 <a href='{APP_URL}'>تطبيق الأندرويد</a> • "
    f"📡 <a href='{CHANNEL_URL}'>قناتنا على تلجرام</a>"
)

# مجموعة الروابط التي تم نشرها لتفادي التكرار
seen_links = set()

# ================= دوال مساعدة =================

def clean_text(s: str) -> str:
    """تنظيف النص من HTML والمسافات الزائدة."""
    if not s:
        return ""
    s = unescape(s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def get_media(entry):
    """
    تحاول استخراج فيديو أو صورة من الـ RSS.
    تعيد: (type, url)  type = 'video' أو 'photo' أو None
    """
    # أولوية للفيديو ثم الصورة
    # 1) media_content
    media_fields = []
    if "media_content" in entry:
        media_fields.extend(entry.media_content)
    if "media_thumbnail" in entry:
        media_fields.extend(entry.media_thumbnail)
    if "enclosures" in entry:
        media_fields.extend(entry.enclosures)

    for item in media_fields:
        try:
            url = item.get("url") or item.get("href")
            mtype = (item.get("type") or "").lower()
            if url and url.startswith("http"):
                if "video" in mtype:
                    return "video", url
        except Exception:
            continue

    for item in media_fields:
        try:
            url = item.get("url") or item.get("href")
            mtype = (item.get("type") or "").lower()
            if url and url.startswith("http"):
                if "image" in mtype or "jpg" in url or "png" in url or "jpeg" in url:
                    return "photo", url
        except Exception:
            continue

    # 2) صورة داخل الـ summary كـ <img>
    if "summary" in entry:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.summary)
        if m:
            return "photo", m.group(1)

    return None, None

def translate_to_ar(title: str, body: str, lang: str):
    """
    ترجمة العنوان والنص إلى العربية إذا كان المصدر غير عربي.
    تعيد: (title_ar, body_ar, original_text_or_none)
    """
    title = title or ""
    body = body or ""

    if lang == "ar":
        # لا حاجة للترجمة
        return title, body, None

    # النص الأصلي (سنضعه في أسفل الرسالة)
    original = f"{title}\n\n{body}".strip()

    try:
        # نترجم العنوان والنص منفصلين لنتحكم بشكل أفضل
        title_ar = translator.translate(title or body, dest="ar").text
        body_ar = translator.translate(body or title, dest="ar").text
    except Exception:
        # لو فشلت الترجمة نرجع النص الأصلي
        return title, body, original

    return title_ar, body_ar, original

def build_caption(title_ar, body_ar, source_name, link, original_text=None):
    """
    يبني نص الرسالة النهائي لإرساله إلى تلجرام.
    """
    source_name = clean_text(source_name)

    # لتفادي تجاوز حد التليجرام في الكابشن (خاصة مع الصور/الفيديو)
    if len(body_ar) > 1500:
        body_ar = body_ar[:1500] + "…"

    caption = f"🔴 <b>{clean_text(title_ar)}</b>\n\n{body_ar}\n\n"
    caption += "____________________\n"
    caption += f"🛰️ <b>المصدر:</b> {source_name}\n"
    if link:
        caption += f"🔗 <a href='{link}'>رابط الخبر</a>\n"
    caption += FOOTER

    # خيار (ب): إضافة النص الأصلي أسفل الترجمة
    if original_text:
        if len(original_text) > 1200:
            original_text = original_text[:1200] + "…"
        caption += f"\n\n🌍 <b>النص الأصلي:</b>\n{clean_text(original_text)}"

    return caption

def send_article(entry, source_name, lang):
    """إرسال خبر واحد إلى قناة تلجرام بشكل منسق."""
    link = entry.get("link", "") or ""
    title = entry.get("title", "") or ""

    # نحاول أخذ تفاصيل كاملة من summary أو description
    raw_body = (
        entry.get("summary")
        or entry.get("description")
        or ""
    )
    body = clean_text(raw_body)

    # ترجمة إذا كان المصدر عبري/إنجليزي
    title_ar, body_ar, original_text = translate_to_ar(title, body, lang)

    if not body_ar:
        body_ar = "التفاصيل غير متاحة بالكامل من المصدر."

    caption = build_caption(title_ar, body_ar, source_name, link, original_text)

    media_type, media_url = get_media(entry)

    try:
        if media_type == "video" and media_url:
            # فيديو في الأعلى
            data = {
                "chat_id": CHAT_ID,
                "video": media_url,
                "caption": caption,
                "parse_mode": "HTML"
            }
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
                data=data,
                timeout=20
            )
        elif media_type == "photo" and media_url:
            # صورة في الأعلى
            data = {
                "chat_id": CHAT_ID,
                "photo": media_url,
                "caption": caption,
                "parse_mode": "HTML"
            }
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data=data,
                timeout=20
            )
        else:
            # خبر نصي فقط
            data = {
                "chat_id": CHAT_ID,
                "text": caption,
                "parse_mode": "HTML"
            }
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data=data,
                timeout=20
            )

        print(f"✅ نُشر خبر: {title_ar[:60]}…")
    except Exception as e:
        print(f"⚠️ خطأ أثناء الإرسال: {e}")

# ================= حلقة تشغيل البوت =================

def run_bot():
    print("🚀 F90 News Bot يعمل الآن… (مع ترجمة وأولوية للأخبار الفلسطينية)")
    while True:
        new_count = 0

        for src in SOURCES:
            url = src["url"]
            lang = src["lang"]

            try:
                feed = feedparser.parse(url)
                source_name = feed.feed.get("title", "خبر عاجل")

                # نقرأ من الأقدم للأحدث حتى يكون الترتيب منطقي
                for entry in reversed(feed.entries):
                    link = entry.get("link")
                    if not link or link in seen_links:
                        continue

                    seen_links.add(link)   # منع التكرار تماماً
                    send_article(entry, source_name, lang)
                    new_count += 1
                    time.sleep(3)  # مهلة بسيطة بين كل خبر وآخر

            except Exception as e:
                print(f"⚠️ خطأ في المصدر ({url}): {e}")

        if new_count == 0:
            print("⏸️ لا أخبار جديدة حالياً، الانتظار 60 ثانية…")
        time.sleep(60)

# ================= خادم صغير لـ Render / UptimeRobot =================

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ F90 News Bot يعمل الآن 24/7 مع ترجمة وأولوية لأخبار فلسطين."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ================= تشغيل البوت + السيرفر معاً =================

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
