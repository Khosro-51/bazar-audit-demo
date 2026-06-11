"""
Bazar Audit — v1.1 (Private Beta)
Multilingual: English (default) | فارسی | العربية
Engine stays language-agnostic. Translation lives here only.

v1.1:
- Access Code gate (st.secrets["ACCESS_CODE"] → env BAZAR_ACCESS_CODE → default)
- Private Upload Beta: one free audit per email (sha256 hash in beta_usage.json)
- Visible APP_VERSION in sidebar for deploy verification
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from html import escape
import pandas as pd
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ── Config ────────────────────────────────────────────────────────────────────
DEMO_MODE = True
APP_VERSION = "v1.1"

# Access code: اول st.secrets، بعد env، بعد مقدار پیش‌فرض.
# برای production مقدار را در Streamlit Cloud → App settings → Secrets بگذار:
#   ACCESS_CODE = "..."
DEFAULT_ACCESS_CODE = "BZR-9T4K-72QX"

BETA_USAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beta_usage.json")
MAX_UPLOAD_MB   = 5

SAMPLE_FILES = {
    "good":    os.path.join(BASE_DIR, "sample_data", "bazar_sample_good_trader.csv"),
    "average": os.path.join(BASE_DIR, "sample_data", "bazar_sample_average_trader.csv"),
    "problem": os.path.join(BASE_DIR, "sample_data", "bazar_sample_behavior_problem_trader.csv"),
}

REQUIRED_COLS    = {'open_time', 'close_time', 'symbol', 'side', 'pnl', 'session'}
RECOMMENDED_COLS = {
    'pnl_R', 'lot_or_size', 'commission', 'balance_before', 'balance_after',
    'initial_risk_amount', 'initial_sl', 'setup_tag', 'exit_reason',
    'mfe_R', 'mae_R', 'trade_index_in_day',
}
UPLOAD_REQUIRED_COLS = {'trade_id'} | REQUIRED_COLS
SEV_ICON = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}

# ── Language System ───────────────────────────────────────────────────────────
LANGS = {"en": "English", "fa": "فارسی", "ar": "العربية"}
RTL_LANGS = {"fa", "ar"}

T = {
    "en": {
        "title":            "Bazar Audit",
        "language":         "Language",
        "app_version":      "v1.1 — Private Beta",
        "subtitle":         "Discover what really drives your trading performance.",
        "disclaimer":       "Bazar does not provide buy/sell signals or financial advice. It analyzes trading performance, risk behavior, and strategy structure.",
        "pick_profile":     "Choose a sample trader profile",
        "pick_caption":     "Three realistic profiles — see how Bazar thinks.",
        "good_label":       "✅ Good Trader",
        "good_narrative":   "No critical issues detected. Keep tracking more data.",
        "avg_label":        "⚠️ Average Trader",
        "avg_narrative":    "Main issues: session toxicity, fast re-entry after losses, weak symbol selection.",
        "prob_label":       "🔴 Problem Trader",
        "prob_narrative":   "First problem is not behavior. Core strategy is structurally below breakeven.",
        "choose_prompt":    "👆 Select one of the profiles above to generate an Audit Report.",
        "analyzing":        "Analyzing...",
        "health_summary":   "Trading Health Summary",
        "trades":           "Trades",
        "high_issues":      "🔴 High Issues",
        "med_issues":       "🟠 Medium Issues",
        "low_issues":       "🟢 Low Issues",
        "win_rate":         "Win Rate",
        "profit_factor":    "Profit Factor",
        "expectancy":       "Expectancy",
        "no_issues":        "✅ No significant issues detected.",
        "insights_header":  "Top Insights",
        "rec_action":       "Recommended Action",
        "metric_snap":      "Metric Snapshot",
        "bazar_says":       "Bazar says",
        "tab_report":       "📋 Audit Report",
        "tab_data":         "📁 Data",
        "tab_json":         "🔧 JSON",
        "filter_symbol":    "Filter by symbol",
        "all":              "All",
        "total_rows":       "Total Rows",
        "columns":          "Columns",
        "col_info":         "Column Info",
        "json_title":       "Engine Output — Raw JSON",
        "json_download":    "⬇️ Download Audit JSON",
        "demo_note":        "🔒 **Demo Mode** — Upload CSV available in private beta.",
        "sidebar_desc":     "Discover what really drives your trading performance.\n\nBazar does not provide buy/sell signals.\nIt analyzes trading behavior and strategy structure.",
        "required_cols":    "Required columns",
        "recommended_cols": "Recommended columns",
        "upload_label":     "Upload your trade history CSV",
        "upload_format":    "Sample CSV format",
        "sample_load_error": "Error loading sample",
        "csv_not_readable": "CSV is not readable.",
        "missing_required": "Missing required columns",
        "missing_recommended": "Missing recommended columns",
        "engine_import_error": "Engine import failed.",
        "engine_error":     "Engine error.",
        "trade_data":       "Trade Data",
        "insight_meta_conf": "conf",
        "insight_meta_n":   "n",
        "r_warning":        "pnl_R not found. R-based insights are disabled. Add initial_risk_amount or pnl_R for full analysis.",
        "coming_soon":      "📌 Upload your own trading history — coming soon for private beta.",
        "access_title":     "🔒 Private Access",
        "access_label":     "Enter access code",
        "access_btn":       "Unlock",
        "access_wrong":     "Invalid access code.",
        "beta_header":      "🔬 Private Upload Beta",
        "beta_privacy":     "You can upload one CSV file and receive one free Bazar Audit report. Bazar does not store your trading file in this demo. Do not upload sensitive live account data.",
        "beta_email_label": "Your email",
        "beta_invalid_email": "Please enter a valid email address.",
        "beta_file_too_big": "File exceeds the 5MB limit.",
        "beta_already_used": "You have already used your free audit. Join the private beta to unlock more reports.",
    },
    "fa": {
        "title":            "بازار آدیت",
        "language":         "زبان",
        "app_version":      "نسخه v1.1 — بتای خصوصی",
        "subtitle":         "بفهم سود و ضرر معاملاتت واقعاً از کجا می‌آید.",
        "disclaimer":       "Bazar سیگنال خرید و فروش یا مشاوره سرمایه‌گذاری ارائه نمی‌دهد. Bazar عملکرد معاملاتی، رفتار ریسک و ساختار استراتژی را تحلیل می‌کند.",
        "pick_profile":     "یک تریدر نمونه را انتخاب کن",
        "pick_caption":     "سه پروفایل واقع‌گرایانه — ببین Bazar چطور فکر می‌کند.",
        "good_label":       "✅ تریدر خوب",
        "good_narrative":   "هیچ مشکل قابل توجهی شناسایی نشد. به ثبت معاملات ادامه بده.",
        "avg_label":        "⚠️ تریدر متوسط",
        "avg_narrative":    "مشکلات اصلی: سمیّت سشن، ورود سریع بعد از ضرر، ضعف در انتخاب نماد.",
        "prob_label":       "🔴 تریدر با مشکل",
        "prob_narrative":   "مشکل اول رفتاری نیست. استراتژی اصلی از نظر ساختاری زیر سطح سر به سر است.",
        "choose_prompt":    "👆 یکی از پروفایل‌های بالا را انتخاب کن تا Audit Report ساخته شود.",
        "analyzing":        "در حال تحلیل...",
        "health_summary":   "خلاصه سلامت معاملاتی",
        "trades":           "معاملات",
        "high_issues":      "🔴 مشکلات بحرانی",
        "med_issues":       "🟠 هشدارها",
        "low_issues":       "🟢 نکات سبک",
        "win_rate":         "نرخ برد",
        "profit_factor":    "ضریب سود",
        "expectancy":       "انتظار",
        "no_issues":        "✅ هیچ مشکل قابل توجهی شناسایی نشد.",
        "insights_header":  "مهم‌ترین بینش‌ها",
        "rec_action":       "اقدام پیشنهادی",
        "metric_snap":      "جزئیات عددی",
        "bazar_says":       "Bazar می‌گوید",
        "tab_report":       "📋 گزارش آدیت",
        "tab_data":         "📁 داده‌ها",
        "tab_json":         "🔧 JSON",
        "filter_symbol":    "فیلتر نماد",
        "all":              "همه",
        "total_rows":       "تعداد کل",
        "columns":          "ستون‌ها",
        "col_info":         "اطلاعات ستون‌ها",
        "json_title":       "خروجی Engine — JSON خام",
        "json_download":    "⬇️ دانلود JSON آدیت",
        "demo_note":        "🔒 **حالت دمو** — آپلود CSV در نسخه بتا فعال می‌شود.",
        "sidebar_desc":     "بفهم سود و ضرر معاملاتت واقعاً از کجا می‌آید.\n\nBazar سیگنال خرید/فروش نمی‌دهد.\nعملکرد، ریسک و ساختار تصمیم‌گیری تریدر را تحلیل می‌کند.",
        "required_cols":    "ستون‌های اجباری",
        "recommended_cols": "ستون‌های پیشنهادی",
        "upload_label":     "فایل CSV معاملاتت را آپلود کن",
        "upload_format":    "نمونه فرمت CSV",
        "sample_load_error": "خطا در بارگذاری فایل نمونه",
        "csv_not_readable": "CSV قابل خواندن نیست.",
        "missing_required": "ستون‌های اجباری وجود ندارند",
        "missing_recommended": "ستون‌های پیشنهادی موجود نیستند",
        "engine_import_error": "بارگذاری Engine ناموفق بود.",
        "engine_error":     "Engine خطا داد.",
        "trade_data":       "داده‌های معامله",
        "insight_meta_conf": "اطمینان",
        "insight_meta_n":   "تعداد",
        "r_warning":        "ستون pnl_R پیدا نشد. بینش‌های مبتنی بر R غیرفعال هستند. برای تحلیل کامل، initial_risk_amount یا pnl_R را اضافه کن.",
        "coming_soon":      "📌 آپلود تاریخچه معاملاتت — به‌زودی در نسخه بتا.",
        "access_title":     "🔒 ورود خصوصی",
        "access_label":     "کد دسترسی را وارد کن",
        "access_btn":       "باز کردن",
        "access_wrong":     "کد دسترسی نادرست است.",
        "beta_header":      "🔬 آپلود خصوصی (بتا)",
        "beta_privacy":     "شما می‌توانید یک فایل CSV آپلود کنید و یک گزارش رایگان Bazar Audit دریافت کنید. Bazar در این نسخه نمایشی فایل معاملاتی شما را ذخیره نمی‌کند. از آپلود اطلاعات حساس حساب واقعی خودداری کنید.",
        "beta_email_label": "ایمیل شما",
        "beta_invalid_email": "یک ایمیل معتبر وارد کن.",
        "beta_file_too_big": "حجم فایل بیشتر از حد مجاز ۵ مگابایت است.",
        "beta_already_used": "شما گزارش رایگان خود را قبلاً استفاده کرده‌اید. برای گزارش‌های بیشتر به بتای خصوصی بپیوندید.",
    },
    "ar": {
        "title":            "Bazar Audit",
        "language":         "اللغة",
        "app_version":      "v1.1 — نسخة تجريبية خاصة",
        "subtitle":         "اكتشف ما الذي يقود أداء تداولك فعلياً.",
        "disclaimer":       "لا يقدم Bazar إشارات شراء أو بيع ولا نصائح استثمارية. يقوم Bazar بتحليل أداء التداول وسلوك المخاطر وبنية الاستراتيجية.",
        "pick_profile":     "اختر ملف متداول نموذجياً",
        "pick_caption":     "ثلاثة ملفات واقعية — انظر كيف يفكر Bazar.",
        "good_label":       "✅ متداول جيد",
        "good_narrative":   "لم يتم رصد أي مشكلة جوهرية. استمر في تتبع المزيد من الصفقات.",
        "avg_label":        "⚠️ متداول متوسط",
        "avg_narrative":    "المشكلات الرئيسية: سمية الجلسة، الدخول السريع بعد الخسارة، ضعف اختيار الرمز.",
        "prob_label":       "🔴 متداول يعاني من مشاكل",
        "prob_narrative":   "المشكلة الأولى ليست سلوكية. الاستراتيجية الأساسية هيكلياً دون نقطة التعادل.",
        "choose_prompt":    "👆 اختر أحد الملفات أعلاه لإنشاء تقرير التدقيق.",
        "analyzing":        "جارٍ التحليل...",
        "health_summary":   "ملخص صحة التداول",
        "trades":           "الصفقات",
        "high_issues":      "🔴 مشاكل حرجة",
        "med_issues":       "🟠 تحذيرات",
        "low_issues":       "🟢 ملاحظات خفيفة",
        "win_rate":         "نسبة الفوز",
        "profit_factor":    "معامل الربح",
        "expectancy":       "التوقع",
        "no_issues":        "✅ لم يتم رصد أي مشكلة جوهرية.",
        "insights_header":  "أهم الرؤى",
        "rec_action":       "الإجراء المقترح",
        "metric_snap":      "لقطة المقاييس",
        "bazar_says":       "يقول Bazar",
        "tab_report":       "📋 تقرير التدقيق",
        "tab_data":         "📁 البيانات",
        "tab_json":         "🔧 JSON",
        "filter_symbol":    "تصفية حسب الرمز",
        "all":              "الكل",
        "total_rows":       "إجمالي الصفوف",
        "columns":          "الأعمدة",
        "col_info":         "معلومات الأعمدة",
        "json_title":       "مخرجات المحرك — JSON الخام",
        "json_download":    "⬇️ تنزيل JSON",
        "demo_note":        "🔒 **وضع العرض التوضيحي** — رفع CSV متاح في النسخة التجريبية.",
        "sidebar_desc":     "اكتشف ما الذي يقود أداء تداولك فعلياً.\n\nلا يقدم Bazar إشارات شراء أو بيع.\nيحلل سلوك التداول وأداء الاستراتيجية.",
        "required_cols":    "الأعمدة المطلوبة",
        "recommended_cols": "الأعمدة المقترحة",
        "upload_label":     "ارفع ملف CSV لتاريخ تداولك",
        "upload_format":    "نموذج تنسيق CSV",
        "sample_load_error": "خطأ في تحميل العينة",
        "csv_not_readable": "ملف CSV غير قابل للقراءة.",
        "missing_required": "الأعمدة المطلوبة غير موجودة",
        "missing_recommended": "الأعمدة المقترحة غير موجودة",
        "engine_import_error": "فشل تحميل المحرك.",
        "engine_error":     "خطأ في المحرك.",
        "trade_data":       "بيانات الصفقات",
        "insight_meta_conf": "الثقة",
        "insight_meta_n":   "العدد",
        "r_warning":        "لم يتم العثور على pnl_R. تم تعطيل الرؤى المعتمدة على R. أضف initial_risk_amount أو pnl_R للتحليل الكامل.",
        "coming_soon":      "📌 رفع تاريخ تداولك الخاص — قريباً في النسخة التجريبية.",
        "access_title":     "🔒 دخول خاص",
        "access_label":     "أدخل رمز الوصول",
        "access_btn":       "فتح",
        "access_wrong":     "رمز الوصول غير صحيح.",
        "beta_header":      "🔬 رفع خاص (تجريبي)",
        "beta_privacy":     "يمكنك رفع ملف CSV واحد والحصول على تقرير Bazar Audit مجاني واحد. لا يقوم Bazar بتخزين ملف التداول الخاص بك في هذه النسخة التجريبية. يرجى عدم رفع بيانات حساسة لحساب تداول حقيقي.",
        "beta_email_label": "بريدك الإلكتروني",
        "beta_invalid_email": "يرجى إدخال بريد إلكتروني صالح.",
        "beta_file_too_big": "حجم الملف يتجاوز الحد 5MB.",
        "beta_already_used": "لقد استخدمت تقريرك المجاني بالفعل. انضم إلى النسخة التجريبية الخاصة للحصول على المزيد من التقارير.",
    },
}

# ── Insight Translations ──────────────────────────────────────────────────────
INSIGHT_T = {
    "SYSTEMIC_UNDERPERFORMANCE": {
        "en": {"title": "Systemic Underperformance",
               "body_key": "message"},
        "fa": {"title": "ضعف ساختاری استراتژی",
               "body_key": "body_fa"},
        "ar": {"title": "ضعف هيكلي في الاستراتيجية",
               "body": "يبدو أن أداء استراتيجيتك الحالية أقل من مستوى التعادل بشكل هيكلي. راجع منطق الدخول والخروج الأساسي قبل تحسين القواعد السلوكية."},
    },
    "SESSION_TOXICITY": {
        "en": {"title": "Session Toxicity",           "body_key": "message"},
        "fa": {"title": "سمیّت سشن",                  "body_key": "body_fa"},
        "ar": {"title": "سمية الجلسة",
               "body": "إحدى جلسات تداولك تُدر خسائر منتظمة. تجنب التداول خلالها أو قلّل حجمه."},
    },
    "TRADE_COUNT_CLIFF": {
        "en": {"title": "Trade Count Cliff",          "body_key": "message"},
        "fa": {"title": "سقوط بعد از معامله n‌ام",    "body_key": "body_fa"},
        "ar": {"title": "انهيار نسبة الفوز بعد الصفقة N",
               "body": "تنخفض نسبة فوزك بشكل حاد بعد صفقة معينة كل يوم. ضع حداً صارماً لعدد الصفقات اليومية."},
    },
    "POST_LOSS_DECAY": {
        "en": {"title": "Post-Loss Performance Decay", "body_key": "message"},
        "fa": {"title": "افت عملکرد بعد از ضرر",       "body_key": "body_fa"},
        "ar": {"title": "تراجع الأداء بعد الخسارة",
               "body": "تنخفض جودة صفقاتك بعد الخسائر. طبّق فترة راحة إلزامية بعد كل خسارة."},
    },
    "POST_LOSS_FAST_REENTRY": {
        "en": {"title": "Fast Re-Entry After Loss",   "body_key": "message"},
        "fa": {"title": "ورود سریع بعد از ضرر",       "body_key": "body_fa"},
        "ar": {"title": "إعادة الدخول السريعة بعد الخسارة",
               "body": "الدخول خلال 60 دقيقة من الخسارة يُضعف أداءك. التزم بفترة تهدئة."},
    },
    "DRAWDOWN_RECOVERY_SIZING": {
        "en": {"title": "Drawdown Recovery Oversizing", "body_key": "message"},
        "fa": {"title": "بزرگ کردن سایز در drawdown",  "body_key": "body_fa"},
        "ar": {"title": "تضخيم الحجم أثناء التراجع",
               "body": "تزداد أحجام صفقاتك خلال فترات التراجع. التزم بنسبة مخاطرة ثابتة."},
    },
    "PAYOFF_IMBALANCE": {
        "en": {"title": "Payoff Imbalance",           "body_key": "message"},
        "fa": {"title": "عدم تعادل سود/ضرر",          "body_key": "body_fa"},
        "ar": {"title": "اختلال في نسبة العائد",
               "body": "متوسط ربحك أصغر من متوسط خسارتك. دع الصفقات الرابحة تجري وأغلق الخاسرة بسرعة."},
    },
    "SYMBOL_NO_EDGE": {
        "en": {"title": "No Edge on Symbol",          "body_key": "message"},
        "fa": {"title": "فاقد edge در نماد",           "body_key": "body_fa"},
        "ar": {"title": "لا ميزة على هذا الرمز",
               "body": "لا توجد ميزة إحصائية على أحد الرموز. أزله من خطة تداولك أو تدرّب عليه على الورق أولاً."},
    },
    "SAMPLE_SIZE_LIMITED": {
        "en": {"title": "Limited Sample Size",        "body_key": "message"},
        "fa": {"title": "حجم نمونه محدود",             "body_key": "body_fa"},
        "ar": {"title": "حجم عينة محدود",
               "body": "عدد الصفقات كافٍ للتحليل الأساسي لكن يُنصح بـ 100+ صفقة للحصول على رؤى أعمق."},
    },
    "SAMPLE_SIZE_INSUFFICIENT": {
        "en": {"title": "Insufficient Data",          "body_key": "message"},
        "fa": {"title": "داده کافی نیست",              "body_key": "body_fa"},
        "ar": {"title": "بيانات غير كافية",
               "body": "عدد الصفقات غير كافٍ للتحليل الموثوق. الحد الأدنى 30 صفقة."},
    },
}

ACTION_T = {
    "SYSTEMIC_UNDERPERFORMANCE": {
        "fa": "قبل از بهینه‌سازی قوانین رفتاری، منطق اصلی ورود و خروج را بازبینی کن.",
        "ar": "راجع منطق الدخول والخروج الأساسي قبل تحسين القواعد السلوكية.",
    },
    "SESSION_TOXICITY": {
        "fa": "معامله در این سشن را حذف یا به‌شدت محدود کن.",
        "ar": "تجنب التداول في هذه الجلسة أو قلّله بشكل واضح.",
    },
    "TRADE_COUNT_CLIFF": {
        "fa": "برای هر روز معاملاتی یک سقف سخت برای تعداد معاملات تعیین کن.",
        "ar": "ضع حداً صارماً لعدد الصفقات في كل يوم تداول.",
    },
    "POST_LOSS_DECAY": {
        "fa": "بعد از هر ضرر، قبل از ورود دوباره یک فرایند بازبینی ساختاری داشته باش.",
        "ar": "طبّق مراجعة منظمة قبل الدخول مرة أخرى بعد الخسارة.",
    },
    "POST_LOSS_FAST_REENTRY": {
        "fa": "بعد از هر معامله زیان‌ده، حداقل ۶۰ دقیقه cooldown اجباری بگذار.",
        "ar": "أضف فترة تهدئة إلزامية مدتها 60 دقيقة بعد كل صفقة خاسرة.",
    },
    "DRAWDOWN_RECOVERY_SIZING": {
        "fa": "سایز پوزیشن را بر اساس درصد ریسک ثابت نگه دار، نه وضعیت حساب.",
        "ar": "ثبّت حجم الصفقة كنسبة مخاطرة ثابتة بغض النظر عن حالة الحساب.",
    },
    "PAYOFF_IMBALANCE": {
        "fa": "استراتژی خروج را بازبینی کن؛ به برنده‌ها فضای رشد بده و بازنده‌ها را سریع‌تر ببند.",
        "ar": "راجع استراتيجية الخروج؛ اترك الرابحين يمتدون واقطع الخاسرين أسرع.",
    },
    "SYMBOL_NO_EDGE": {
        "fa": "این نماد را از پلن معاملاتی حذف کن یا فعلاً فقط paper-trade کن.",
        "ar": "أزل هذا الرمز من خطة التداول أو تدرّب عليه أولاً بحساب تجريبي.",
    },
    "SAMPLE_SIZE_LIMITED": {
        "fa": "برای رسیدن به تحلیل عمیق‌تر، ثبت معاملات را تا ۱۰۰+ معامله ادامه بده.",
        "ar": "واصل تسجيل الصفقات حتى تصل إلى 100+ صفقة للحصول على رؤى أعمق.",
    },
    "SAMPLE_SIZE_INSUFFICIENT": {
        "fa": "ثبت معاملات را ادامه بده؛ حداقل ۳۰ معامله لازم است و ۱۰۰+ توصیه می‌شود.",
        "ar": "واصل تسجيل الصفقات؛ الحد الأدنى 30 صفقة ويُفضل 100+.",
    },
}


def safe(value) -> str:
    return escape(str(value), quote=True)


def translate_warning(warning: str, lang: str) -> str:
    if "pnl_R not found" in warning:
        return T[lang]["r_warning"]
    return warning


def get_insight_text(ins: dict, lang: str) -> tuple:
    iid = ins.get("insight_id", "")
    t   = INSIGHT_T.get(iid, {}).get(lang, {})

    if lang == "en":
        title = t.get("title") or ins.get("insight_id", "")
    elif lang == "fa":
        title = ins.get("title_fa") or t.get("title") or iid
    else:
        title = t.get("title") or iid

    if "body" in t:
        body = t["body"]
    elif t.get("body_key") == "message":
        body = ins.get("message", "")
    else:
        body = ins.get("body_fa") or ins.get("message", "")

    action = ins.get("recommended_action", "")
    if lang in {"fa", "ar"}:
        action = ACTION_T.get(iid, {}).get(lang, action)

    return title, body, action


# ── Engine Import ─────────────────────────────────────────────────────────────
# ── Access Code + Beta Usage Helpers (v1.1) ───────────────────────────────────

def get_access_code() -> str:
    """اولویت: st.secrets[ACCESS_CODE] → env BAZAR_ACCESS_CODE → مقدار پیش‌فرض در کد."""
    try:
        if "ACCESS_CODE" in st.secrets:
            return str(st.secrets["ACCESS_CODE"]).strip()
    except Exception:
        pass
    return os.getenv("BAZAR_ACCESS_CODE", DEFAULT_ACCESS_CODE).strip()


def email_hash(email: str) -> str:
    """sha256 از ایمیل trim+lowercase شده — ایمیل خام هیچ‌جا ذخیره نمی‌شود."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def load_beta_usage() -> dict:
    try:
        with open(BETA_USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_beta_usage(usage: dict) -> None:
    try:
        with open(BETA_USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(usage, f, indent=2)
    except Exception:
        pass  # روی Streamlit Cloud فایل‌سیستم موقتی است؛ برای production از DB استفاده شود.


ENGINE_ERROR = None
try:
    from bazar_audit_engine import audit_from_df
except Exception as e:
    audit_from_df = None
    ENGINE_ERROR  = e

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bazar Audit",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Language State ────────────────────────────────────────────────────────────
if "lang" not in st.session_state:
    st.session_state["lang"] = "en"

# ── RTL/LTR CSS ───────────────────────────────────────────────────────────────
def apply_direction(lang: str):
    if lang in RTL_LANGS:
        st.markdown("""
<style>
html, body, [class*="css"], .stMarkdown, .stText, .stAlert, .stCaption,
.stMetric, .stExpander, .stTabs { direction: rtl; text-align: right; }
div[data-testid="metric-container"] > div { text-align: right; }
.language-switcher, .language-switcher * { direction: ltr; text-align: left; }
.disclaimer { border-left: 0 !important; border-right: 3px solid #334155; padding-left: 0 !important; padding-right: 10px; }
.sample-narrative { border-left: 0 !important; border-right: 4px solid #475569; }
.sample-narrative.good { border-right-color: #34d399; }
.sample-narrative.average { border-right-color: #fbbf24; }
.sample-narrative.problem { border-right-color: #f87171; }
.ins-card { border-left-width: 1px !important; }
.ins-card.HIGH { border-right: 5px solid #f87171; }
.ins-card.MEDIUM { border-right: 5px solid #fbbf24; }
.ins-card.LOW { border-right: 5px solid #34d399; }
.ins-action { border-left: 0 !important; border-right: 3px solid #60a5fa; padding-left: 0 !important; padding-right: 10px; }
</style>""", unsafe_allow_html=True)
    else:
        st.markdown("""
<style>
html, body, [class*="css"] { direction: ltr; text-align: left; }
.language-switcher, .language-switcher * { direction: ltr; text-align: left; }
</style>""", unsafe_allow_html=True)

# ── Base CSS ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .hero-title {
    font-size: 2.6rem; font-weight: 700; line-height: 1.2;
    background: linear-gradient(135deg, #a78bfa, #60a5fa, #34d399);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.25rem;
  }
  .hero-sub  { font-size: 1.05rem; color: #94a3b8; margin-bottom: 1.5rem; }
  .disclaimer {
    font-size: 0.78rem; color: #64748b;
    border-left: 3px solid #334155; padding-left: 10px;
    margin-bottom: 1.5rem; line-height: 1.6;
  }
  .sample-narrative {
    background: #1e293b; border-radius: 10px;
    padding: 14px 18px; margin-top: 6px;
    font-size: 0.88rem; color: #cbd5e1; line-height: 1.6;
    border-left: 4px solid #475569;
  }
  .sample-narrative.good    { border-color: #34d399; }
  .sample-narrative.average { border-color: #fbbf24; }
  .sample-narrative.problem { border-color: #f87171; }
  div[data-testid="metric-container"] {
    background: #1e293b; border-radius: 10px;
    padding: 14px 16px; border: 1px solid #334155;
  }
  .ins-card {
    border-radius: 10px; padding: 16px 20px;
    margin-bottom: 14px; border: 1px solid #334155;
    background: #1e293b;
  }
  .ins-card.HIGH   { border-left: 5px solid #f87171; }
  .ins-card.MEDIUM { border-left: 5px solid #fbbf24; }
  .ins-card.LOW    { border-left: 5px solid #34d399; }
  .ins-title { font-size: 1.05rem; font-weight: 600; margin-bottom: 4px; }
  .ins-body  { font-size: 0.9rem; color: #cbd5e1; line-height: 1.65; }
  .ins-action {
    font-size: 0.85rem; color: #60a5fa;
    border-left: 3px solid #60a5fa; padding-left: 10px; margin-top: 10px;
  }
  .ins-badge { display:inline-block; border-radius:4px; padding:2px 8px;
    font-size:0.72rem; font-weight:600; margin-right:6px; vertical-align:middle; }
  .badge-HIGH   { background:#7f1d1d; color:#fca5a5; }
  .badge-MEDIUM { background:#78350f; color:#fcd34d; }
  .badge-LOW    { background:#064e3b; color:#6ee7b7; }
  .language-switcher {
    margin: 0 0 18px 0;
    max-width: 520px;
  }
  section[data-testid="stSidebar"] { background: #0f172a; }
</style>
""", unsafe_allow_html=True)

# ── Engine Check ──────────────────────────────────────────────────────────────
if ENGINE_ERROR or audit_from_df is None:
    st.error(f"⚠️ {T[st.session_state['lang']]['engine_import_error']}")
    st.exception(ENGINE_ERROR)
    st.stop()

st.markdown('<div class="language-switcher">', unsafe_allow_html=True)
selected_lang = st.radio(
    T[st.session_state["lang"]]["language"],
    options=list(LANGS.keys()),
    format_func=lambda code: LANGS[code],
    horizontal=True,
    index=list(LANGS.keys()).index(st.session_state["lang"]),
    key="language_selector",
)
st.markdown("</div>", unsafe_allow_html=True)

# Render this same run with the newly selected language. Streamlit already
# reruns on widget changes, so avoid an extra manual rerun that resets the page.
st.session_state["lang"] = selected_lang
lang = selected_lang
tx = T[lang]
apply_direction(lang)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Bazar Audit")
    st.markdown(f"**{tx['app_version']}**")
    st.divider()
    st.markdown(tx["sidebar_desc"])
    st.divider()
    if DEMO_MODE:
        st.info(tx["demo_note"])
    else:
        st.markdown(f"**{tx['required_cols']}:**")
        st.code(", ".join(sorted(REQUIRED_COLS)))
        st.markdown(f"**{tx['recommended_cols']}:**")
        st.code(", ".join(sorted(RECOMMENDED_COLS)))
    st.divider()
    st.caption(tx["disclaimer"])

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown(f'<div class="hero-title">{safe(tx["title"])}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="hero-sub">{safe(tx["subtitle"])}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="disclaimer">{safe(tx["disclaimer"])}</div>', unsafe_allow_html=True)

# ── Sample Picker / Upload ────────────────────────────────────────────────────
# ── Access Gate (v1.1): بدون کد دسترسی، هیچ‌چیز باز نمی‌شود ─────────────────────
if not st.session_state.get("access_granted", False):
    st.subheader(tx["access_title"])
    code_in = st.text_input(tx["access_label"], type="password", key="access_input")
    if st.button(tx["access_btn"], key="access_submit"):
        if code_in.strip() == get_access_code():
            st.session_state["access_granted"] = True
            st.rerun()
        else:
            st.error(tx["access_wrong"])
    st.stop()

if DEMO_MODE:
    st.subheader(tx["pick_profile"])
    st.caption(tx["pick_caption"])

    col_g, col_a, col_p = st.columns(3)
    chosen = None

    with col_g:
        if st.button(tx["good_label"], use_container_width=True, key="btn_good"):
            chosen = "good"
        st.markdown(f'<div class="sample-narrative good">{safe(tx["good_narrative"])}</div>',
                    unsafe_allow_html=True)
    with col_a:
        if st.button(tx["avg_label"], use_container_width=True, key="btn_average"):
            chosen = "average"
        st.markdown(f'<div class="sample-narrative average">{safe(tx["avg_narrative"])}</div>',
                    unsafe_allow_html=True)
    with col_p:
        if st.button(tx["prob_label"], use_container_width=True, key="btn_problem"):
            chosen = "problem"
        st.markdown(f'<div class="sample-narrative problem">{safe(tx["prob_narrative"])}</div>',
                    unsafe_allow_html=True)

    # ── Private Upload Beta (v1.1) ────────────────────────────────────────
    st.divider()
    st.subheader(tx["beta_header"])
    st.caption(tx["beta_privacy"])

    col_e, col_u = st.columns([1, 2])
    with col_e:
        beta_email = st.text_input(tx["beta_email_label"], key="beta_email")
    with col_u:
        beta_file = st.file_uploader(tx["upload_label"], type=["csv"], key="beta_uploader")

    if "active_sample" not in st.session_state:
        st.session_state.active_sample = None
    if chosen:
        st.session_state.active_sample = chosen
        st.session_state["view"] = "sample"

    if beta_file is not None:
        email_ok = bool(beta_email) and "@" in beta_email and "." in beta_email.split("@")[-1]
        if not email_ok:
            st.warning(tx["beta_invalid_email"])
        elif beta_file.size > MAX_UPLOAD_MB * 1024 * 1024:
            st.error(tx["beta_file_too_big"])
        else:
            h = email_hash(beta_email)
            already_this_session = (
                st.session_state.get("beta_hash") == h
                and st.session_state.get("beta_df") is not None
            )
            if not already_this_session:
                usage = load_beta_usage()
                if h in usage:
                    st.error(tx["beta_already_used"])
                else:
                    bdf = None
                    try:
                        # فقط در حافظه خوانده می‌شود؛ فایل CSV ذخیره نمی‌شود.
                        bdf = pd.read_csv(beta_file, parse_dates=['open_time', 'close_time'])
                    except Exception:
                        st.error(tx["csv_not_readable"])
                    if bdf is not None:
                        missing = sorted(UPLOAD_REQUIRED_COLS - set(bdf.columns))
                        if missing:
                            st.error(f"{tx['missing_required']}: `{', '.join(missing)}`")
                        else:
                            now = datetime.now(timezone.utc).isoformat()
                            usage[h] = {"upload_count": 1,
                                        "first_upload_at": now,
                                        "last_upload_at": now}
                            save_beta_usage(usage)
                            st.session_state["beta_df"] = bdf.sort_values('open_time').reset_index(drop=True)
                            st.session_state["beta_hash"] = h
                            st.session_state["beta_trader_id"] = beta_file.name.replace('.csv', '')
                            st.session_state["view"] = "upload"

    # ── انتخاب منبع نمایش: آپلود کاربر یا پروفایل نمونه ──────────────────────
    view = st.session_state.get("view")
    if view == "upload" and st.session_state.get("beta_df") is not None:
        df        = st.session_state["beta_df"]
        trader_id = st.session_state.get("beta_trader_id", "beta_user")
        source    = "upload"
    elif st.session_state.active_sample is not None:
        key      = st.session_state.active_sample
        csv_path = SAMPLE_FILES[key]
        trader_id = key.upper() + "_TRADER"
        try:
            df = pd.read_csv(csv_path, parse_dates=['open_time', 'close_time'])
            df = df.sort_values('open_time').reset_index(drop=True)
        except Exception as e:
            st.error(f"{tx['sample_load_error']}: {e}")
            st.stop()
        source = "sample"
    else:
        st.info(tx["choose_prompt"])
        st.stop()

else:
    uploaded = st.file_uploader(tx["upload_label"], type=["csv"])
    if uploaded is None:
        with st.expander(tx["upload_format"]):
            sample = pd.DataFrame([{
                "trade_id": "T001", "open_time": "2024-01-05 09:00:00",
                "close_time": "2024-01-05 09:45:00", "symbol": "EURUSD",
                "side": "BUY", "pnl": 120.5, "pnl_R": 1.2,
                "session": "London", "lot_or_size": 0.1,
            }])
            st.dataframe(sample)
        st.stop()
    try:
        df = pd.read_csv(uploaded, parse_dates=['open_time', 'close_time'])
        df = df.sort_values('open_time').reset_index(drop=True)
    except Exception as e:
        st.error(tx["csv_not_readable"])
        st.exception(e)
        st.stop()
    missing_req = sorted(REQUIRED_COLS - set(df.columns))
    if missing_req:
        st.error(f"{tx['missing_required']}: `{', '.join(missing_req)}`")
        st.stop()
    missing_rec = sorted(RECOMMENDED_COLS - set(df.columns))
    if missing_rec:
        with st.expander(f"⚠️ {tx['missing_recommended']}"):
            st.warning(f"`{', '.join(missing_rec)}`")
    trader_id = uploaded.name.replace('.csv', '')
    source = "upload"

# ── Run Engine ────────────────────────────────────────────────────────────────
with st.spinner(tx["analyzing"]):
    try:
        report = audit_from_df(df, trader_id=trader_id)
        result = report.to_dict()
    except Exception as e:
        st.error(tx["engine_error"])
        st.exception(e)
        st.stop()

insights = result.get("insights", [])
metrics  = result.get("core_metrics", {})

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_report, tab_data, tab_json = st.tabs([tx["tab_report"], tx["tab_data"], tx["tab_json"]])

# ════════════════════════════════════════════════════════════════════════════
with tab_report:

    # narrative banner — فقط برای پروفایل‌های نمونه، نه آپلود کاربر
    if DEMO_MODE and source == "sample":
        key = st.session_state.active_sample
        narrative_map = {"good": tx["good_narrative"], "average": tx["avg_narrative"], "problem": tx["prob_narrative"]}
        color_map     = {"good": "#34d399", "average": "#fbbf24", "problem": "#f87171"}
        st.markdown(f"""
        <div style="background:#1e293b;border-left:5px solid {color_map[key]};
                    border-radius:8px;padding:14px 20px;margin-bottom:18px;
                    font-size:0.95rem;color:#e2e8f0;">
            <strong>{safe(tx['bazar_says'])}:</strong> {safe(narrative_map[key])}
        </div>
        """, unsafe_allow_html=True)

    st.subheader(tx["health_summary"])

    high_n   = sum(1 for i in insights if i.get("severity") == "HIGH")
    medium_n = sum(1 for i in insights if i.get("severity") == "MEDIUM")
    wr  = metrics.get("win_rate", 0)
    pf  = metrics.get("profit_factor", 0)
    exp_r = metrics.get("expectancy_R")
    exp_d = metrics.get("expectancy_dollar", 0)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric(tx["trades"],       f"{report.total_trades}")
    c2.metric(tx["high_issues"],  f"{high_n}")
    c3.metric(tx["med_issues"],   f"{medium_n}")
    c4.metric(tx["win_rate"],     f"{wr*100:.1f}%" if wr else "N/A")
    c5.metric(tx["profit_factor"],f"{pf:.2f}" if pf else "N/A")
    c6.metric(tx["expectancy"],   f"{exp_r:.2f}R" if exp_r is not None else f"{exp_d:.1f}$")

    if result.get("warnings"):
        for w in result["warnings"]:
            st.warning(translate_warning(w, lang))

    st.divider()

    if not insights:
        st.success(tx["no_issues"])
    else:
        st.subheader(f"{tx['insights_header']} — {len(insights)}")
        for ins in insights:
            sev   = ins.get("severity", "LOW")
            iid   = ins.get("insight_id", "")
            conf  = ins.get("confidence", "")
            n     = ins.get("sample_size", "")
            snap  = ins.get("metric_snapshot", {})
            icon  = SEV_ICON.get(sev, "⚪")

            title, body, action = get_insight_text(ins, lang)
            action_html = ""
            if action:
                action_html = (
                    f'<div class="ins-action"><strong>{safe(tx["rec_action"])}:</strong> '
                    f'{safe(action)}</div>'
                )

            st.markdown(f"""
            <div class="ins-card {sev}">
              <div class="ins-title">
                {icon}&nbsp;{safe(title)}
                <span class="ins-badge badge-{sev}">{sev}</span>
                <span style="font-size:0.72rem;color:#64748b;">{safe(iid)} | {safe(tx['insight_meta_conf'])}:{safe(conf)} | {safe(tx['insight_meta_n'])}={safe(n)}</span>
              </div>
              <div class="ins-body">{safe(body)}</div>
              {action_html}
            </div>
            """, unsafe_allow_html=True)

            if snap:
                with st.expander(tx["metric_snap"]):
                    num_items = {k: v for k, v in snap.items()
                                 if isinstance(v, (int, float)) and not isinstance(v, bool)}
                    if num_items:
                        cols = st.columns(min(len(num_items), 4))
                        for i, (k, v) in enumerate(num_items.items()):
                            cols[i % 4].metric(k, f"{v:.3f}" if isinstance(v, float) else str(v))
                    complex_items = {k: v for k, v in snap.items()
                                     if not isinstance(v, (int, float, type(None))) or isinstance(v, bool)}
                    if complex_items:
                        st.json(complex_items)

# ════════════════════════════════════════════════════════════════════════════
with tab_data:
    st.subheader(tx["trade_data"])
    col_f, col_i = st.columns([2, 1])
    with col_f:
        if 'symbol' in df.columns:
            symbols = [tx["all"]] + sorted(df['symbol'].unique().tolist())
            sel_sym = st.selectbox(tx["filter_symbol"], symbols)
        else:
            sel_sym = tx["all"]
    with col_i:
        st.metric(tx["total_rows"], len(df))
        st.metric(tx["columns"],    len(df.columns))

    display_df = df if sel_sym == tx["all"] else df[df['symbol'] == sel_sym]
    st.dataframe(display_df, use_container_width=True, height=400)

    st.divider()
    st.subheader(tx["col_info"])
    col_info_df = pd.DataFrame({
        "column":   list(df.columns),
        "non_null": [int(df[c].notna().sum()) for c in df.columns],
        "dtype":    [str(df[c].dtype)         for c in df.columns],
        "sample":   [str(df[c].iloc[0]) if len(df) > 0 else "" for c in df.columns],
    })
    st.dataframe(col_info_df, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
with tab_json:
    st.subheader(tx["json_title"])
    st.json(result)
    st.download_button(
        label=tx["json_download"],
        data=json.dumps(result, ensure_ascii=False, indent=2, default=str),
        file_name=f"bazar_audit_{trader_id}.json",
        mime="application/json",
    )
