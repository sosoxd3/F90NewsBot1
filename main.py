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

BOT_TOKEN = os.getenv("BOT_TOKEN", "8340084044:AAH4xDclN0yKECmpTFcnL5eshA4-qREHw4w")
CHAT_ID = os.getenv("CHAT_ID", "@f90newsnow")

# نفس المصادر السابقة + عدة مواقع فلسطينية/عربية قوية
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

# ذيل ثابت أسفل كل خبر
FOOTER = (
    "\n\n———\n"
    "📢 انضموا لنا لتَروا الأخبار لحظة بلحظة\n"
    "🌐 موقعنا الرسمي: https://e9dd-009-80041-a80rjkupq6lz-deployed-internal.easysite.ai/\n"
    "📱 تحميل تطبيق الأندرويد: https://newoaks.s3.us-west-1.amazonaws.com/AutoDev/80041/d281064b-a82e-4fdf-bc19-d19cc4e0ccd4.apk\n"
    "📡 تابعنا على تلجرام: https://t.me/f90newsnow"
)

# منع التكرار
seen_links = set()
seen_titles = set()
SEEN_LIMIT = 5000

# متابعة آخر مرة أرسلنا فيها أسعار العملات
last_fx_time = 0  # timestamp

# ============================
#   دوال مساعدة
# ============================

def clean_html(raw: str) -> str:
    """إزالة الوسوم والروابط وتنسيق المسافات"""
    if not raw:
        return ""
    raw = unescape(raw)
    raw = re.sub(r"<[^>]+>", " ", raw)      # إزالة HTML
    raw = re.sub(r"http\S+", "", raw)       # إزالة أي روابط داخل النص
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def get_full_text(entry) -> str:
    """استخراج النص الكامل للخبر من الـ RSS"""
    if "summary" in entry:
        return clean_html(entry.summary)
    if "description" in entry:
        return clean_html(entry.description)
    return ""


def get_image(entry):
    """محاولة الحصول على صورة من عناصر الـ RSS"""
    for key in ("media_content", "media_thumbnail", "enclosures"):
        if key in entry:
            try:
                data = entry[key][0] if isinstance(entry[key], list) else entry[key]
                url = data.get("url") or data.get("href")
                if url and url.startswith("http") and not url.endswith(".mp4"):
                    return url
            except Exception:
                pass
    return None


def get_video(entry):
    """محاولة الحصول على فيديو (mp4) إن وُجد"""
    for key in ("media_content", "enclosures"):
        if key in entry:
            items = entry[key] if isinstance(entry[key], list) else [entry[key]]
            for it in items:
                url = it.get("url") or it.get("href")
                if url and url.startswith("http") and url.endswith(".mp4"):
                    return url

    # محاولة التقاط mp4 من النص نفسه
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
    links = re.findall(r"(https?://\S+)", summary)
    for l in links:
        if l.endswith(".mp4"):
            return l

    return None


def get_entry_datetime(entry):
    """
    نحاول معرفة وقت نشر الخبر من الحقول:
    published_parsed أو updated_parsed
    إذا لم نجد، نرجّع None
    """
    for key in ("published_parsed", "updated_parsed"):
        if key in entry and entry[key]:
            try:
                tt = entry[key]
                return datetime(*tt[:6])
            except Exception:
                continue
    return None


def is_recent(entry, hours=24):
    """فقط الأخبار خلال آخر (hours) ساعة"""
    dt = get_entry_datetime(entry)
    if not dt:
        # لو ما في وقت واضح، نعتبره حديث مرة واحدة فقط
        return True
    return (datetime.utcnow() - dt) <= timedelta(hours=hours)


def shrink_seen_sets():
    """تقليل حجم قوائم التكرار لو كبرت جدا"""
    global seen_links, seen_titles
    if len(seen_links) > SEEN_LIMIT:
        seen_links = set(list(seen_links)[-SEEN_LIMIT // 2:])
    if len(seen_titles) > SEEN_LIMIT:
        seen_titles = set(list(seen_titles)[-SEEN_LIMIT // 2:])


# ============================
#   إرسال الأخبار
# ============================

def send_news(title, source, details, img=None, video=None):
    """إرسال خبر واحد (عنوان + تفاصيل + صورة/فيديو + فوتر)"""

    caption = (
        f"🔴 <b>{title}</b>\n\n"
        f"📄 <b>التفاصيل:</b>\n{details}\n\n"
        f"📰 <i>{source}</i>"
        f"{FOOTER}"
    )

    # فيديو أولاً إن وجد
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
            print("⚠️ فشل إرسال الفيديو، نرسل صورة/نص فقط:", e)

    # ثم صورة
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
            print("⚠️ فشل إرسال الصورة، نرسل نص فقط:", e)

    # وإلا نص فقط
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
    )


# ============================
#   أسعار العملات مقابل الشيكل
# ============================

def fetch_fx_rates():
    """
    نجلب الأسعار التقريبية من API مجاني (exchangerate.host)
    ثم نحسب سعر الشراء والبيع بشكل تقديري.
    """
    try:
        # 1 شيكل = X دولار / يورو / دينار
        url = "https://api.exchangerate.host/latest?base=ILS&symbols=USD,EUR,JOD"
        res = requests.get(url, timeout=10)
        data = res.json()
        rates = data.get("rates", {})

        usd_per_ils = rates.get("USD")
        eur_per_ils = rates.get("EUR")
        jod_per_ils = rates.get("JOD")

        if not (usd_per_ils and eur_per_ils and jod_per_ils):
            return None

        # نعكس حتى يصبح (كم شيكل لكل 1 عملة)
        usd_ils = round(1 / usd_per_ils, 3)
        eur_ils = round(1 / eur_per_ils, 3)
        jod_ils = round(1 / jod_per_ils, 3)

        # بيع و شراء تقريبية (سبريد 1%)
        def buy_sell(mid):
            buy = round(mid * 1.01, 3)   # شراء من الزبون (أعلى قليلاً)
            sell = round(mid * 0.99, 3)  # بيع للزبون (أقل قليلاً)
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
            "ℹ️ الأرقام تقريبية حسب أسعار الصرف العالمية، "
            "وليست أسعار سوق محلي أو صرافة معينة."
        )

        return text
    except Exception as e:
        print("⚠️ خطأ في جلب أسعار العملات:", e)
        return None


def send_fx_if_needed():
    """إرسال أسعار العملات مرة كل 24 ساعة فقط"""
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
    print("🚀 F90 News Bot (الإصدار الجديد) يعمل الآن…")
    while True:
        shrink_seen_sets()
        new_count = 0

        # أولاً: أسعار العملات (لو مرّ أكثر من 24 ساعة)
        send_fx_if_needed()

        # ثانياً: الأخبار
        for url in SOURCES:
            try:
                feed = feedparser.parse(url)
                source = feed.feed.get("title", "مصدر إخباري")

                # نقرأ من الأقدم إلى الأحدث حتى يكون التسلسل منطقي
                for entry in reversed(feed.entries):

                    # فلتر زمني: آخر 24 ساعة فقط
                    if not is_recent(entry, hours=24):
                        continue

                    link = entry.get("link", "")
                    if not link:
                        continue

                    title = clean_html(entry.get("title", "خبر عاجل"))
                    if not title:
                        continue

                    key_title = title.lower()

                    # منع التكرار تماماً
                    if link in seen_links or key_title in seen_titles:
                        continue

                    details = get_full_text(entry)
                    if len(details) < 30:
                        # خبر قصير جداً، نتجاهله
                        continue

                    img = get_image(entry)
                    vid = get_video(entry)

                    send_news(title, source, details, img, vid)

                    seen_links.add(link)
                    seen_titles.add(key_title)
                    new_count += 1

                    time.sleep(2)  # مهلة بين كل خبر

            except Exception as e:
                print("⚠️ خطأ أثناء قراءة المصدر:", e)

        if new_count == 0:
            print("⏸️ لا أخبار جديدة حقيقية الآن، البوت في وضع انتظار…")

        # انتظار دقيقة ثم إعادة المحاولة
        time.sleep(60)


# ============================
#   Flask ليبقى البوت حي على Render
# ============================

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ F90 News Bot يعمل الآن 24/7 – الإصدار الجديد بدون تكرار وبدون أخبار قديمة."

def run_flask():
    app.run(host="0.0.0.0", port=8080)


if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()
