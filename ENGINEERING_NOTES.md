در پروژه Bazar Audit Demo، قبل از هر تغییری اول کد دسترسی فعلی اپ را پیدا و حفظ کن.

مهم:
- اپ نباید عمومی و بدون قفل شود.
- Access Code فعلی باید قبل از تغییر استخراج شود.
- بعد از تغییر، اپ باید همچنان با همان Access Code قبلی فعال شود.
- اگر Access Code در streamlit_app.py، st.secrets، environment variable، .streamlit/secrets.toml، README یا هر فایل config دیگری تعریف شده، محل دقیق آن را پیدا کن.
- مقدار Access Code را تغییر نده.
- اگر مقدار access code در فایل secret/local قرار دارد، آن را داخل git commit نبر.
- اگر hardcoded است، فعلاً برای جلوگیری از شکستن demo همان را حفظ کن، ولی در گزارش نهایی بگو بهتر است بعداً به Streamlit Secrets منتقل شود.

هدف تغییر:
Private Upload Beta را اضافه کن، اما فقط بعد از ورود با Access Code.

جریان نهایی اپ باید این باشد:

1. کاربر وارد اپ می‌شود.
2. اول باید Access Code فعلی را وارد کند.
3. اگر Access Code درست بود، اپ باز شود.
4. کاربر سه sample demo را همچنان ببیند:
   - Good Trader
   - Average Trader
   - Problem Trader
5. علاوه بر sample demo، بخش Private Upload Beta هم نمایش داده شود.
6. در Private Upload Beta کاربر باید email وارد کند.
7. هر email فقط یک بار بتواند CSV آپلود و audit بگیرد.
8. بعد از اولین audit موفق، همان email دیگر اجازه upload مجدد نداشته باشد.
9. اگر email قبلاً استفاده شده بود، پیام بده:
   "You have already used your free audit. Join the private beta to unlock more reports."
10. Upload عمومی بدون access code ممنوع است.

پیاده‌سازی access:
- تابعی بساز مثل:
  require_access_code()
- این تابع باید از همان Access Code فعلی استفاده کند.
- اگر Access Code فعلی از st.secrets یا os.getenv خوانده می‌شود، همان روش را حفظ کن.
- اگر در کد hardcoded است، همان مقدار را دست‌نخورده نگه دار.
- بعد از ورود موفق، وضعیت در st.session_state ذخیره شود:
  st.session_state["access_granted"] = True

پیاده‌سازی Email Gate:
- برای MVP فعلی، اگر دیتابیس نداریم، یک فایل محلی ساده بساز:
  beta_usage.json
- این فایل باید email_hash ذخیره کند، نه email خام.
- از sha256 برای hash ایمیل استفاده کن.
- email را trim و lowercase کن قبل از hash.
- ساختار beta_usage.json:
  {
    "email_hash": {
      "upload_count": 1,
      "first_upload_at": "...",
      "last_upload_at": "..."
    }
  }

مهم:
- فایل CSV کاربر ذخیره نشود.
- فقط در حافظه خوانده و audit شود.
- فقط email hash و upload_count ذخیره شود.
- اگر روی Streamlit Cloud فایل محلی persistent نبود، در README توضیح بده که برای production باید Supabase/PostgreSQL استفاده شود.
- فعلاً برای private beta کنترل‌شده همین کافی است.

UI Requirements:
- English باید default باشد.
- Language toggle فعلی English | فارسی | العربية حفظ شود.
- RTL برای فارسی و عربی حفظ شود.
- Disclaimer باید حفظ شود:
  "Bazar does not provide buy/sell signals or financial advice. It analyzes trading performance, risk behavior, and strategy structure."
- برای بخش upload متن privacy اضافه کن:
  English:
  "You can upload one CSV file and receive one free Bazar Audit report. Bazar does not store your trading file in this demo. Do not upload sensitive live account data."
  Persian:
  "شما می‌توانید یک فایل CSV آپلود کنید و یک گزارش رایگان Bazar Audit دریافت کنید. Bazar در این نسخه نمایشی فایل معاملاتی شما را ذخیره نمی‌کند. از آپلود اطلاعات حساس حساب واقعی خودداری کنید."
  Arabic:
  "يمكنك رفع ملف CSV واحد والحصول على تقرير Bazar Audit مجاني واحد. لا يقوم Bazar بتخزين ملف التداول الخاص بك في هذه النسخة التجريبية. يرجى عدم رفع بيانات حساسة لحساب تداول حقيقي."

Upload Validation:
- فقط CSV قبول شود.
- حداکثر حجم فایل 5MB باشد.
- ستون‌های ضروری:
  trade_id
  open_time
  close_time
  symbol
  pnl
- اگر ستون ضروری نبود، audit اجرا نشود و خطای واضح بده.
- اگر pnl_R نبود، تحلیل محدود شود و warning بده که R-based insights ممکن است محدود باشند.
- auto-parse زمان‌ها در audit_from_df حفظ شود.

Insight Engine:
- فایل‌های frozen را فقط اگر لازم است تغییر بده.
- JSON contract نباید بشکند.
- هر insight همچنان این فیلدها را داشته باشد:
  insight_id
  severity
  confidence
  sample_size
  metric_snapshot
  message
  recommended_action
  title_fa
  body_fa

Sample Demo نباید خراب شود:
بعد از تغییر، این سه سناریو باید دقیقاً pass شوند:

GOOD:
- فقط SAMPLE_SIZE_LIMITED
- 0 HIGH
- 0 MEDIUM

AVERAGE:
- SESSION_TOXICITY
- SYMBOL_NO_EDGE
- POST_LOSS_FAST_REENTRY
- SYSTEMIC_UNDERPERFORMANCE inactive

PROBLEM:
- SYSTEMIC_UNDERPERFORMANCE باید اولین insight باشد
- بعد SESSION_TOXICITY
- بعد TRADE_COUNT_CLIFF
- بعد PAYOFF_IMBALANCE
- SYMBOL_NO_EDGE هم فعال باشد

Tests:
- قبل از commit اجرا کن:
  python -m pytest tests/test_all.py
- اگر test شکست خورد، commit نکن.
- بعد از test موفق، streamlit را اجرا کن:
  streamlit run streamlit_app.py
- دستی چک کن:
  1. بدون access code اپ باز نشود.
  2. با همان access code قبلی اپ باز شود.
  3. سه sample demo درست کار کنند.
  4. upload با email جدید فقط یک بار کار کند.
  5. همان email برای بار دوم block شود.
  6. فایل CSV ذخیره نشود.
  7. beta_usage.json فقط email_hash ذخیره کند، نه email خام.

Git:
- بعد از موفقیت کامل:
  git status
  git add .
  git commit -m "Add gated private upload beta"
  git push

گزارش نهایی بده:
- Access Code از کجا خوانده شد.
- آیا مقدار آن حفظ شد یا نه.
- چه فایل‌هایی تغییر کردند.
- تست‌ها pass شدند یا نه.
- Private Upload Beta دقیقاً چطور فعال می‌شود.