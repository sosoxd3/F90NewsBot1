import feedparser
import requests
import time
import re
from html import unescape
import os
import threading
from datetime import datetime, timedelta
from flask import Flask
from deep_translator import GoogleTranslator  # للترجمة التلقائية

# ============================
#   إعدادات البوت
# ============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8340084044:AAH4xDclN0yKECmpTFcnL5eshA4-qREHw4w")
CHAT_ID = os.getenv("CHAT_ID", "@f90newsnow")

SOURCES = [
    # فلسطين / غزة أولاً
    "https://shehabnews.com/ar/rss.xml",
    "https://qudsn.co/feed",
    "https://maannews.net/rss/ar.xml",

    # الجزيرة (تغطي فلسطين والعالم)
    "https://www.aljazeera.net/xml/rss/all.xml",

    # باقي المصادر العربية
    "https://www.skynewsarabia.com/web/rss",
    "https://arabic.rt.com/rss/",
    "https://www.alarabiya.net/.mrss/ar.xml",
    "https://www.bbc.com/arabic/index.xml",
    "https://www.asharqnews.com/ar/rss.xml",

    # مصادر إنجليزية/عالمية (ستُترجم للعربية)
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
]

FOOTER_links = (
    "____________________\n"
    "🔔 انضموا لنا لقراءة الأخبار لحظة بلحظة\n"
    "🌐 <a href='https://e9dd-009-80041-a80rjkupq6lz-deployed-internal.easysite.ai/'>موقعنا الرسمي</a>\n"
    "📱 <a href='https://newoaks.s3.us-west-1.amazonaws.com/AutoDev/80041/d281064b-a82e-4fdf-bc19-d19cc4e0ccd4.apk'>تحميل تطبيق الأندرويد</a>\n"
    "📡 <a href='https://t.me/f90newsnow'>تابعنا على تلجرام</a>"
            "📢 تابعوا البث المباشر الان\n"
    "📡 قناة الرياضة: @F90Sports\n"
    "📡 قناة الرياضة: @F90newsnow\n"
    "\n🎥 <b>بث مباشر مباريات اليوم:</b>\n"
    f"🔗 <a href=\"{DIRECT_LINK}\">اضغط هنا</a>\n"
)

seen_links = set()
seen_titles = set()
SEEN_LIMIT = 5000

last_fx_time = 0  # لأسعار العملات (مرة كل 24 ساعة)

# ============================
#   دوال مساعدة
# ============================

def clean_html(raw: str) -> str:
    if not raw:
        return ""
    raw = unescape(raw)
    raw = re.sub(r"<[^>]+>", " ", raw)      # إزالة HTML
    raw = re.sub(r"http\S+", "", raw)       # إزالة أي روابط
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
            except Exception:
                pass
    # صورة من الـ summary
    if "summary" in entry:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.summary)
        if m:
            return m.group(1)
    return None

def get_video(entry):
    for key in ("media_content", "enclosures"):
        if key in entry:
            items = entry[key] if isinstance(entry[key], list) else [entry[key]]
            for it in items:
                url = it.get("url") or it.get("href")
                if url and url.startswith("http") and url.endswith(".mp4"):
                    return url

    summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
    links = re.findall(r"(https?://\S+)", summary)
    for l in links:
        if l.endswith(".mp4"):
            return l

    return None

def get_entry_datetime(entry):
    for key in ("published_parsed", "updated_parsed"):
        if key in entry and entry[key]:
            try:
                tt = entry[key]
                return datetime(*tt[:6])
            except Exception:
                continue
    return None

def is_recent(entry, hours=24):
    dt = get_entry_datetime(entry)
    if not dt:
        # لو ما في تاريخ، نعتبره قديم ونتركه
        return False
    return (datetime.utcnow() - dt) <= timedelta(hours=hours)

def shrink_seen_sets():
    global seen_links, seen_titles
    if len(seen_links) > SEEN_LIMIT:
        seen_links = set(list(seen_links)[-SEEN_LIMIT // 2:])
    if len(seen_titles) > SEEN_LIMIT:
        seen_titles = set(list(seen_titles)[-SEEN_LIMIT // 2:])

# ============================
#   الترجمة التلقائية (إنجليزي/عبري → عربي)
# ============================

def translate_if_needed(title: str, details: str):
    text = (title or "") + " " + (details or "")
    hebrew = re.search(r"[\u0590-\u05FF]", text)
    english = re.search(r"[A-Za-z]", text)

    if not hebrew and not english:
        # عربي أصلاً
        return title, details, None

    original = (title or "") + "\n\n" + (details or "")
    try:
        t_title = GoogleTranslator(source="auto", target="ar").translate(title or details)
        t_details = GoogleTranslator(source="auto", target="ar").translate(details or title)
        return t_title, t_details, original.strip()
    except Exception as e:
        print("⚠️ فشل الترجمة:", e)
        return title, details, None

# ============================
#   إرسال الأخبار
# ============================

def send_news(title, source, details, link, img=None, video=None, original=None):
    # قص النص قليلاً لو في صورة/فيديو (محدودية الكابشن في تيليجرام)
    body = details or ""
    if (img or video) and len(body) > 900:
        body = body[:900] + "…"

    source_clean = clean_html(source)

    caption = (
        f"🔴 <b>{clean_html(title)}</b>\n\n"
        f"{body}\n\n"
        "____________________\n"
        f"🛰️ <b>المصدر:</b> {source_clean}\n"
    )

    if link:
        caption += f"📎 <a href='{link}'>رابط الخبر</a>\n"

    caption += FOOTER_links

    if original:
        # إضافة النص الأصلي بالأسفل (مختصر)
        orig = clean_html(original)
        if len(orig) > 1000:
            orig = orig[:1000] + "…"
        caption += f"\n\n🌍 <b>النص الأصلي:</b>\n{orig}"

    # فيديو أولاً
    if video:
        try:
            vdata = requests.get(video, timeout=15).content
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
                data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                files={"video": vdata}
            )
            return
        except Exception as e:
            print("⚠️ فشل إرسال الفيديو:", e)

    # صورة
    if img:
        try:
            pdata = requests.get(img, timeout=10).content
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                files={"photo": pdata}
            )
            return
        except Exception as e:
            print("⚠️ فشل إرسال الصورة:", e)

    # نص فقط
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
    )

# ============================
#   أسعار العملات مقابل الشيكل
# ============================

def fetch_fx_rates():
    try:
        url = "https://api.exchangerate.host/latest?base=ILS&symbols=USD,EUR,JOD"
        res = requests.get(url, timeout=10)
        data = res.json()
        rates = data.get("rates", {})

        usd = rates.get("USD")
        eur = rates.get("EUR")
        jod = rates.get("JOD")
        if not (usd and eur and jod):
            return None

        # نحسب كم شيكل لكل 1 دولار/يورو/دينار
        usd_ils = round(1 / usd, 3)
        eur_ils = round(1 / eur, 3)
        jod_ils = round(1 / jod, 3)

        def buy_sell(mid):
            buy = round(mid * 1.01, 3)
            sell = round(mid * 0.99, 3)
            return buy, sell

        usd_buy, usd_sell = buy_sell(usd_ils)
        eur_buy, eur_sell = buy_sell(eur_ils)
        jod_buy, jod_sell = buy_sell(jod_ils)

        text = (
            "💱 <b>أسعار العملات مقابل الشيكل (تقريبية)</b>\n\n"
            f"💵 دولار أمريكي (USD):\n"
            f"شراء: {usd_buy} ₪  |  بيع: {usd_sell} ₪\n\n"
            f"💶 يورو (EUR):\n"
            f"شراء: {eur_buy} ₪  |  بيع: {eur_sell} ₪\n\n"
            f"💷 دينار أردني (JOD):\n"
            f"شراء: {jod_buy} ₪  |  بيع: {jod_sell} ₪\n\n"
            "ℹ️ الأرقام تقريبية حسب أسعار الصرف العالمية."
        )
        return text
    except Exception as e:
        print("⚠️ خطأ في جلب أسعار العملات:", e)
        return None

def send_fx_if_needed():
    global last_fx_time
    now = time.time()
    if now - last_fx_time < 24 * 3600:
        return

    fx_text = fetch_fx_rates()
    if not fx_text:
        return

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": fx_text, "parse_mode": "HTML"}
    )
    last_fx_time = now
    print("📊 تم إرسال منشور أسعار العملات.")

# ============================
#   حلقة تشغيل الأخبار
# ============================

def run_bot():
    print("🚀 F90 News Bot (الإصدار المطوّر) يعمل الآن…")
    while True:
        shrink_seen_sets()
        send_fx_if_needed()
        new_count = 0

        for url in SOURCES:
            try:
                feed = feedparser.parse(url)
                source = feed.feed.get("title", "مصدر إخباري")

                # من الأقدم للأحدث
                for entry in reversed(feed.entries):
                    if not is_recent(entry, hours=24):
                        continue

                    link = entry.get("link", "")
                    if not link:
                        continue

                    title = clean_html(entry.get("title", "خبر عاجل"))
                    if not title:
                        continue

                    key_title = title.lower()
                    if link in seen_links or key_title in seen_titles:
                        continue

                    details = get_full_text(entry)
                    if len(details) < 30:
                        continue

                    # ترجمة إن لزم
                    t_title, t_details, original = translate_if_needed(title, details)

                    img = get_image(entry)
                    vid = get_video(entry)

                    send_news(t_title, source, t_details, link, img, vid, original)

                    seen_links.add(link)
                    seen_titles.add(key_title)
                    new_count += 1

                    time.sleep(2)

            except Exception as e:
                print("⚠️ خطأ في المصدر:", e)

        if new_count == 0:
            print("⏸️ لا أخبار جديدة الآن، انتظار 60 ثانية…")

        time.sleep(60)

# ============================
#   Flask ليبقى البوت حي على Render
# ============================

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ F90 News Bot يعمل الآن 24/7 — الإصدار المطوّر."

# اختبار يدوي (اختياري)
@app.route("/test")
def test():
    test_msg = (
        "🔴 <b>منشور تجريبي لاختبار البوت</b>\n\n"
        "إذا وصلتك هذه الرسالة في القناة، فالبوت يعمل بشكل صحيح ✅\n"
        f"{FOOTER_links}"
    )
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": test_msg, "parse_mode": "HTML"}
    )
    return "تم إرسال رسالة اختبار إلى القناة."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
