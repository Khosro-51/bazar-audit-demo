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
import streamlit.components.v1 as components

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except Exception:
    HAS_PLOTLY = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ── Config ────────────────────────────────────────────────────────────────────
DEMO_MODE = True
APP_VERSION = "v2.1"

# Access code: اول st.secrets، بعد env، بعد مقدار پیش‌فرض.
# برای production مقدار را در Streamlit Cloud → App settings → Secrets بگذار:
#   ACCESS_CODE = "..."
# v1.6 (چرخش امنیتی): هیچ کد واقعی در سورس نیست — کدهای قبلی (BZR-9T4K... و BZR-T01...) چون
# در فایل‌های متنی pushپذیر نوشته شده بودند سوخته فرض می‌شوند.
# مقادیر واقعی فقط در .streamlit/secrets.toml (لوکال، gitignored) و Streamlit Cloud → Secrets:
#   ACCESS_CODE  = "..."
#   INVITE_CODES = "CODE1,CODE2,..."
DEFAULT_ACCESS_CODE = ""      # خالی = بدون secrets هیچ ورود مدیری ممکن نیست
DEFAULT_INVITE_CODES = []     # خالی = بدون secrets هیچ توکنی معتبر نیست
MAX_UPLOADS_PER_CODE = 3
TOKEN_TTL_HOURS = 24  # v1.4: توکن یکبارمصرف — از اولین فعال‌سازی فقط ۲۴ ساعت معتبر است

BETA_USAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beta_usage.json")
ASSIGN_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "code_assignments.json")
ACCESS_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "access_log.json")
MAX_UPLOAD_MB   = 5

# ── صحنه سه‌بعدی صفحه ورود (Three.js) ────────────────────────────────────────
HERO_3D = """
<div id="bz3d" style="width:100%;height:300px;background:#07090C;border:1px solid #1C2530;
     border-radius:8px;overflow:hidden;position:relative">
  <div style="position:absolute;top:14px;left:18px;font-family:monospace;font-size:10px;
       letter-spacing:3px;color:#00E5A0;z-index:2;opacity:.9">BAZAR · LIVE DIAGNOSTIC SPACE</div>
  <div style="position:absolute;bottom:12px;right:18px;font-family:monospace;font-size:9px;
       letter-spacing:2px;color:#5B6B7C;z-index:2">EDGE · RISK · BEHAVIOR</div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const el = document.getElementById('bz3d');
const W = el.clientWidth, H = el.clientHeight;
const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x07090C, 18, 42);
const cam = new THREE.PerspectiveCamera(60, W/H, .1, 100);
cam.position.set(0, 3.2, 16);
const ren = new THREE.WebGLRenderer({antialias:true});
ren.setSize(W, H); ren.setClearColor(0x07090C);
el.appendChild(ren.domElement);

// کف شبکه‌ای پرسپکتیو
const grid = new THREE.GridHelper(80, 50, 0x00E5A0, 0x10271F);
grid.position.y = -4; scene.add(grid);

// هسته سیمی دولایه (مغز تحلیلگر)
const ico = new THREE.Mesh(
  new THREE.IcosahedronGeometry(3.4, 1),
  new THREE.MeshBasicMaterial({color:0x00E5A0, wireframe:true, transparent:true, opacity:.55}));
scene.add(ico);
const ico2 = new THREE.Mesh(
  new THREE.IcosahedronGeometry(4.6, 0),
  new THREE.MeshBasicMaterial({color:0x0E4534, wireframe:true, transparent:true, opacity:.35}));
scene.add(ico2);

// ذرات معلق داده
const N=900, pos=new Float32Array(N*3);
for(let i=0;i<N*3;i++) pos[i]=(Math.random()-.5)*46;
const pg=new THREE.BufferGeometry();
pg.setAttribute('position', new THREE.BufferAttribute(pos,3));
const pts=new THREE.Points(pg, new THREE.PointsMaterial({color:0x00E5A0,size:.07,transparent:true,opacity:.5}));
scene.add(pts);

// حلقه کندل‌های سه‌بعدی دور هسته
const bars = new THREE.Group();
for(let i=0;i<36;i++){
  const h = .6+Math.random()*2.6;
  const up = Math.random()>.45;
  const m = new THREE.Mesh(new THREE.BoxGeometry(.18,h,.18),
    new THREE.MeshBasicMaterial({color: up?0x00E5A0:0xFF4757, transparent:true, opacity:.8}));
  const a = i/36*Math.PI*2;
  m.position.set(Math.cos(a)*7.5, -4+h/2, Math.sin(a)*7.5);
  bars.add(m);
}
scene.add(bars);

let t=0;
function loop(){
  requestAnimationFrame(loop);
  t+=.004;
  ico.rotation.y=t*1.6; ico.rotation.x=t*.7;
  ico2.rotation.y=-t;   ico2.rotation.x=t*.4;
  pts.rotation.y=t*.25;
  bars.rotation.y=t*.5;
  cam.position.x=Math.sin(t*.6)*1.2;
  cam.lookAt(0,0,0);
  ren.render(scene,cam);
}
loop();
window.addEventListener('resize',()=>{const w=el.clientWidth;ren.setSize(w,H);cam.aspect=w/H;cam.updateProjectionMatrix();});
</script>
"""

# ── بنر زنده Matrix Rain صفحه اصلی (v1.3) ────────────────────────────────────
MATRIX_BG = """
<div id="bzmx" style="position:relative;width:100%;height:280px;background:#07090C;
     border:1px solid #1C2530;border-radius:8px;overflow:hidden">
  <canvas id="mx" style="display:block"></canvas>
  <div style="position:absolute;top:14px;left:18px;font-family:monospace;font-size:10px;
       letter-spacing:3px;color:#00E5A0;opacity:.9">BAZAR · DIAGNOSTIC RAIN</div>
</div>
<script>
const wrap=document.getElementById('bzmx'),cv=document.getElementById('mx'),ctx=cv.getContext('2d');
let W,H;function rs(){W=cv.width=wrap.clientWidth;H=cv.height=wrap.clientHeight;}rs();
window.addEventListener('resize',rs);
const TERM_H=84;const GROUND=()=>H-TERM_H;
const CHARS='アイウエオカキクケコ01$+-*/=%#@&BZRAUDIT';
const MSGS=['> session.toxicity probe','> symbol.edge compute','> payoff.matrix align',
            '> drawdown.guard active','> post-loss.decay trace','> expectancy.R stream',
            '> cliff.detector armed','> audit.pipeline OK'];
let drops=[],cols=[],term=['BAZAR://init diagnostic core','> edge.scan OK'],tick=0;
function loop(){
  ctx.fillStyle='rgba(7,9,12,.18)';ctx.fillRect(0,0,W,H);
  tick++;
  if(tick%3===0)drops.push({x:Math.random()*W,y:-10,v:4+Math.random()*5});
  // باران
  ctx.strokeStyle='rgba(0,229,160,.55)';ctx.lineWidth=1;
  drops=drops.filter(d=>{
    ctx.beginPath();ctx.moveTo(d.x,d.y-8);ctx.lineTo(d.x,d.y);ctx.stroke();
    d.y+=d.v;
    if(d.y>=GROUND()){
      cols.push({x:d.x,y:0,sp:2+Math.random()*2.5,len:6+(Math.random()*14|0),life:140+Math.random()*100});
      return false;}
    return true;});
  // ستون‌های کد ماتریکس
  ctx.font='12px monospace';
  cols=cols.filter(c=>{
    ctx.fillStyle='#9FFFDE';
    ctx.fillText(CHARS[Math.random()*CHARS.length|0],c.x,Math.min(c.y,GROUND()-2));
    ctx.fillStyle='rgba(0,229,160,.8)';
    for(let i=1;i<c.len;i++){const yy=c.y-i*13;
      if(yy>0&&yy<GROUND())ctx.fillText(CHARS[(tick+i)%CHARS.length],c.x,yy);}
    c.y+=c.sp;c.life--;return c.life>0;});
  // ترمینال درخشان پایین
  const gy=GROUND();
  ctx.fillStyle='rgba(5,7,10,.92)';ctx.fillRect(0,gy,W,TERM_H);
  ctx.strokeStyle='rgba(0,229,160,.6)';ctx.strokeRect(.5,gy+.5,W-1,TERM_H-1);
  if(tick%90===0){term.push(MSGS[(tick/90|0)%MSGS.length]);if(term.length>5)term.shift();}
  ctx.shadowColor='#00E5A0';ctx.shadowBlur=10;
  ctx.fillStyle='#00E5A0';ctx.font='11px monospace';
  term.forEach((l,i)=>ctx.fillText(l,12,gy+18+i*14));
  ctx.shadowBlur=0;
  requestAnimationFrame(loop);
}
loop();
</script>
"""

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
        "app_version":      "v2.1 — Private Beta",
        "subtitle":         "Discover what really drives your trading performance.",
        "disclaimer":       "Bazar does not provide buy/sell signals or financial advice. It analyzes trading performance, risk behavior, and strategy structure.",
        "pick_profile":     "Choose a sample trader profile",
        "pick_caption":     "Three realistic profiles — see how Bazar thinks.",
        "good_label":       "✅ Good Trader",
        "good_narrative":   "No critical issues detected. Keep tracking more data.",
        "avg_label":        "⚠️ Average Trader",
        "avg_narrative":    "Behavioral patterns observed: weak session and weak symbol — evidence still limited at this sample size.",
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
        "access_title":     "Private Access",
        "access_label":     "Enter access code",
        "access_btn":       "Unlock",
        "access_wrong":     "Invalid access code.",
        "beta_header":      "Private Upload Beta",
        "beta_privacy":     "You can upload one CSV file and receive one free Bazar Audit report. Bazar does not store your trading file in this demo. Do not upload sensitive live account data.",
        "beta_email_label": "Your email",
        "beta_invalid_email": "Please enter a valid email address.",
        "beta_file_too_big": "File exceeds the 5MB limit.",
        "beta_already_used": "You have already used your free audit. Join the private beta to unlock more reports.",
        "beta_quota_status": "Uploads used with this invite code: {used} of {max}",
        "beta_quota_used":   "This invite code has used all its free audits ({max} of {max}). Contact us to unlock more reports.",
        "req_header":        "Don't have a code?",
        "req_caption":       "Enter your email to receive a free beta access code. Limited capacity — first come, first served.",
        "req_btn":           "Get my free access code",
        "req_code_msg":      "Your personal access code (save it for future logins):",
        "req_use_hint":      "Now enter this code in the field below and press Unlock.",
        "req_full":          "Free beta capacity is full. Paid access is coming soon — leave us your email and we will contact you.",
        "viz3d_header":      "3D Trade Map",
        "viz3d_caption":     "Every trade in 3D space: hour of day × trading day × result. Drag to rotate, scroll to zoom — clusters of red show exactly where your account bleeds.",
        "src_upload_banner": "REPORT SOURCE: YOUR FILE — {name} · {n} trades",
        "src_sample_banner": "REPORT SOURCE: DEMO PROFILE — {name} · {n} trades (not your data)",
        "back_to_upload":    "↩ Back to my file's report",
        "req_exists":        "This email has already been used. Each email gets one free token — a new token will be available with paid access soon.",
        "code_expired":      "This one-time token has already been activated and its validity window (24h) has ended. Contact support for a new token.",
        "beta_email_mismatch": "Uploads are only allowed with the same email that received this access token.",
        "demo_expander":     "Demo profiles (for reference — not your data)",
        "lbl_breakeven":     "Breakeven WR",
        "lbl_sev":           "High / Medium",
        "cf_current":        "CURRENT",
        "cf_without":        "WITHOUT",
        "report_btn":        "Download Full Report",
        "report_hint":       "Opens in any browser — use Print to save as PDF.",
        "report_generated":  "Generated",
        "report_actions":    "Action Plan",
        "score_label":       "BAZAR SCORE",
        "score_caption":     "Transparent formula out of 100: Edge 40 + Consistency 20 + Discipline 25 + Data 15. No black box.",
        "recov_label":       "Recoverable performance (historical)",
        "recov_note":        "From your own past data: removing the weakest segment would have changed the result by this amount. A historical counterfactual — not a promise of future profit.",
        "journey_title":     "Your Bazar journey",
        "journey_1":         "Level 1 — Audit",
        "journey_2":         "Level 2 — Personal Playbook",
        "journey_3":         "Level 3 — Progress Mentor",
        "journey_you":       "YOU ARE HERE",
        "journey_locked":    "COMING",
        "l2_cta_header":     "Turn this audit into your action playbook",
        "l2_cta_caption":    "Level 2 converts these findings into a personal rulebook for your next 30 trades — built only from your own data. Join the waitlist; early testers get first access.",
        "l2_cta_btn":        "Join the Level 2 waitlist",
        "l2_cta_done":       "You're on the Level 2 waitlist. We'll contact you by email.",
        "beta_email_bound":  "This email is already linked to another invite code. Each email can be used with one code only.",
    },
    "fa": {
        "title":            "بازار آدیت",
        "language":         "زبان",
        "app_version":      "نسخه v2.1 — بتای خصوصی",
        "subtitle":         "بفهم سود و ضرر معاملاتت واقعاً از کجا می‌آید.",
        "disclaimer":       "Bazar سیگنال خرید و فروش یا مشاوره سرمایه‌گذاری ارائه نمی‌دهد. Bazar عملکرد معاملاتی، رفتار ریسک و ساختار استراتژی را تحلیل می‌کند.",
        "pick_profile":     "یک تریدر نمونه را انتخاب کن",
        "pick_caption":     "سه پروفایل واقع‌گرایانه — ببین Bazar چطور فکر می‌کند.",
        "good_label":       "✅ تریدر خوب",
        "good_narrative":   "هیچ مشکل قابل توجهی شناسایی نشد. به ثبت معاملات ادامه بده.",
        "avg_label":        "⚠️ تریدر متوسط",
        "avg_narrative":    "الگوهای رفتاری مشاهده‌شده: سشن و نماد ضعیف — شواهد در این حجم نمونه هنوز محدود است.",
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
        "access_title":     "ورود خصوصی",
        "access_label":     "کد دسترسی را وارد کن",
        "access_btn":       "باز کردن",
        "access_wrong":     "کد دسترسی نادرست است.",
        "beta_header":      "آپلود خصوصی (بتا)",
        "beta_privacy":     "شما می‌توانید یک فایل CSV آپلود کنید و یک گزارش رایگان Bazar Audit دریافت کنید. Bazar در این نسخه نمایشی فایل معاملاتی شما را ذخیره نمی‌کند. از آپلود اطلاعات حساس حساب واقعی خودداری کنید.",
        "beta_email_label": "ایمیل شما",
        "beta_invalid_email": "یک ایمیل معتبر وارد کن.",
        "beta_file_too_big": "حجم فایل بیشتر از حد مجاز ۵ مگابایت است.",
        "beta_already_used": "شما گزارش رایگان خود را قبلاً استفاده کرده‌اید. برای گزارش‌های بیشتر به بتای خصوصی بپیوندید.",
        "beta_quota_status": "آپلودهای استفاده‌شده با این کد دعوت: {used} از {max}",
        "beta_quota_used":   "سهمیه این کد دعوت تمام شده است ({max} از {max}). برای گزارش‌های بیشتر با ما تماس بگیرید.",
        "req_header":        "کد نداری؟",
        "req_caption":       "ایمیلت را ثبت کن تا کد دسترسی رایگان بتا بگیری. ظرفیت محدود است — اولویت با ثبت‌نام زودتر.",
        "req_btn":           "دریافت کد دسترسی رایگان",
        "req_code_msg":      "کد دسترسی شخصی شما (برای ورودهای بعدی نگه‌اش دار):",
        "req_use_hint":      "حالا همین کد را در کادر پایین وارد کن و Unlock را بزن.",
        "req_full":          "ظرفیت بتای رایگان تکمیل شده است. دسترسی پولی به‌زودی فعال می‌شود — ایمیلت ثبت شد و با تو تماس می‌گیریم.",
        "viz3d_header":      "نقشه سه‌بعدی معاملات",
        "viz3d_caption":     "هر معامله در فضای سه‌بعدی: ساعت روز × روز معاملاتی × نتیجه. بچرخان و زوم کن — خوشه‌های قرمز دقیقاً جایی است که حسابت خونریزی می‌کند.",
        "src_upload_banner": "منبع گزارش: فایل شما — {name} · {n} معامله",
        "src_sample_banner": "منبع گزارش: پروفایل دمو — {name} · {n} معامله (داده شما نیست)",
        "back_to_upload":    "↩ بازگشت به گزارش فایل من",
        "req_exists":        "این ایمیل قبلاً استفاده شده است. هر ایمیل فقط یک توکن رایگان دارد — توکن جدید به‌زودی با فعال‌سازی دسترسی پولی ارائه می‌شود.",
        "code_expired":      "این توکن یکبارمصرف قبلاً فعال شده و مهلت اعتبارش (۲۴ ساعت) تمام شده است. برای توکن جدید با پشتیبانی تماس بگیر.",
        "beta_email_mismatch": "آپلود فقط با همان ایمیلی مجاز است که با آن توکن ورود دریافت کرده‌ای.",
        "demo_expander":     "پروفایل‌های دمو (فقط برای مقایسه — داده شما نیست)",
        "lbl_breakeven":     "حد سر‌به‌سر",
        "lbl_sev":           "بحرانی / هشدار",
        "cf_current":        "فعلی",
        "cf_without":        "بدون این بخش",
        "report_btn":        "دانلود گزارش کامل",
        "report_hint":       "در هر مرورگری باز می‌شود — برای PDF از Print استفاده کن.",
        "report_generated":  "تاریخ صدور",
        "report_actions":    "برنامه اقدام",
        "score_label":       "نمره بازار",
        "score_caption":     "فرمول شفاف از ۱۰۰: لبه ۴۰ + ثبات ۲۰ + انضباط ۲۵ + داده ۱۵. هیچ جعبه سیاهی در کار نیست.",
        "recov_label":       "عملکرد قابل بازیابی (گذشته‌نگر)",
        "recov_note":        "بر اساس داده گذشته خودت: حذف ضعیف‌ترین بخش، نتیجه را به این اندازه تغییر می‌داد. این محاسبه گذشته‌نگر است — وعده سود آینده نیست.",
        "journey_title":     "مسیر تو در Bazar",
        "journey_1":         "سطح ۱ — آدیت",
        "journey_2":         "سطح ۲ — پلی‌بوک شخصی",
        "journey_3":         "سطح ۳ — منتور پیشرفت",
        "journey_you":       "تو اینجایی",
        "journey_locked":    "به‌زودی",
        "l2_cta_header":     "این آدیت را به پلن اجرایی تبدیل کن",
        "l2_cta_caption":    "سطح ۲ همین یافته‌ها را به یک دفترچه قانون شخصی برای ۳۰ معامله بعدی‌ات تبدیل می‌کند — فقط از داده خودت. به لیست انتظار بپیوند؛ تسترهای اولیه زودتر دسترسی می‌گیرند.",
        "l2_cta_btn":        "عضویت در لیست انتظار سطح ۲",
        "l2_cta_done":       "در لیست انتظار سطح ۲ ثبت شدی. از طریق ایمیل خبرت می‌کنیم.",
        "beta_email_bound":  "این ایمیل قبلاً با کد دعوت دیگری استفاده شده است. هر ایمیل فقط با یک کد قابل استفاده است.",
    },
    "ar": {
        "title":            "Bazar Audit",
        "language":         "اللغة",
        "app_version":      "v2.1 — نسخة تجريبية خاصة",
        "subtitle":         "اكتشف ما الذي يقود أداء تداولك فعلياً.",
        "disclaimer":       "لا يقدم Bazar إشارات شراء أو بيع ولا نصائح استثمارية. يقوم Bazar بتحليل أداء التداول وسلوك المخاطر وبنية الاستراتيجية.",
        "pick_profile":     "اختر ملف متداول نموذجياً",
        "pick_caption":     "ثلاثة ملفات واقعية — انظر كيف يفكر Bazar.",
        "good_label":       "✅ متداول جيد",
        "good_narrative":   "لم يتم رصد أي مشكلة جوهرية. استمر في تتبع المزيد من الصفقات.",
        "avg_label":        "⚠️ متداول متوسط",
        "avg_narrative":    "أنماط سلوكية ملحوظة: جلسة ورمز ضعيفان — الأدلة ما زالت محدودة بهذا الحجم.",
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
        "access_title":     "دخول خاص",
        "access_label":     "أدخل رمز الوصول",
        "access_btn":       "فتح",
        "access_wrong":     "رمز الوصول غير صحيح.",
        "beta_header":      "رفع خاص (تجريبي)",
        "beta_privacy":     "يمكنك رفع ملف CSV واحد والحصول على تقرير Bazar Audit مجاني واحد. لا يقوم Bazar بتخزين ملف التداول الخاص بك في هذه النسخة التجريبية. يرجى عدم رفع بيانات حساسة لحساب تداول حقيقي.",
        "beta_email_label": "بريدك الإلكتروني",
        "beta_invalid_email": "يرجى إدخال بريد إلكتروني صالح.",
        "beta_file_too_big": "حجم الملف يتجاوز الحد 5MB.",
        "beta_already_used": "لقد استخدمت تقريرك المجاني بالفعل. انضم إلى النسخة التجريبية الخاصة للحصول على المزيد من التقارير.",
        "beta_quota_status": "الرفعات المستخدمة بهذا الرمز: {used} من {max}",
        "beta_quota_used":   "استُنفدت حصة هذا الرمز ({max} من {max}). تواصل معنا للحصول على المزيد من التقارير.",
        "req_header":        "ليس لديك رمز؟",
        "req_caption":       "أدخل بريدك الإلكتروني للحصول على رمز وصول مجاني للنسخة التجريبية. السعة محدودة — الأسبقية للأول.",
        "req_btn":           "الحصول على رمز مجاني",
        "req_code_msg":      "رمز الوصول الخاص بك (احتفظ به للدخول لاحقاً):",
        "req_use_hint":      "الآن أدخل هذا الرمز في الحقل أدناه واضغط Unlock.",
        "req_full":          "اكتملت سعة النسخة التجريبية المجانية. الوصول المدفوع قادم قريباً — تم تسجيل بريدك وسنتواصل معك.",
        "viz3d_header":      "خريطة الصفقات ثلاثية الأبعاد",
        "viz3d_caption":     "كل صفقة في فضاء ثلاثي الأبعاد: ساعة اليوم × يوم التداول × النتيجة. أدر وكبّر — التجمعات الحمراء تُظهر أين ينزف حسابك بالضبط.",
        "src_upload_banner": "مصدر التقرير: ملفك — {name} · {n} صفقة",
        "src_sample_banner": "مصدر التقرير: ملف تجريبي — {name} · {n} صفقة (ليست بياناتك)",
        "back_to_upload":    "↩ العودة إلى تقرير ملفي",
        "req_exists":        "هذا البريد استُخدم من قبل. لكل بريد رمز مجاني واحد فقط — رمز جديد سيتوفر قريباً مع الوصول المدفوع.",
        "code_expired":      "هذا الرمز أحادي الاستخدام تم تفعيله سابقاً وانتهت صلاحيته (24 ساعة). تواصل مع الدعم لرمز جديد.",
        "beta_email_mismatch": "الرفع مسموح فقط بنفس البريد الذي حصل على رمز الدخول.",
        "demo_expander":     "ملفات تجريبية (للمقارنة فقط — ليست بياناتك)",
        "lbl_breakeven":     "حد التعادل",
        "lbl_sev":           "حرجة / تحذير",
        "cf_current":        "الحالي",
        "cf_without":        "بدون هذا الجزء",
        "report_btn":        "تنزيل التقرير الكامل",
        "report_hint":       "يُفتح في أي متصفح — استخدم Print للحفظ كـ PDF.",
        "report_generated":  "تاريخ الإصدار",
        "report_actions":    "خطة العمل",
        "score_label":       "درجة بازار",
        "score_caption":     "معادلة شفافة من 100: الأفضلية 40 + الثبات 20 + الانضباط 25 + البيانات 15. لا صندوق أسود.",
        "recov_label":       "أداء قابل للاسترداد (تاريخي)",
        "recov_note":        "وفق بياناتك السابقة: حذف أضعف جزء كان سيغيّر النتيجة بهذا المقدار. حساب تاريخي — ليس وعداً بربح مستقبلي.",
        "journey_title":     "رحلتك في Bazar",
        "journey_1":         "المستوى 1 — التدقيق",
        "journey_2":         "المستوى 2 — دفتر قواعد شخصي",
        "journey_3":         "المستوى 3 — مرشد التقدم",
        "journey_you":       "أنت هنا",
        "journey_locked":    "قريباً",
        "l2_cta_header":     "حوّل هذا التدقيق إلى خطة تنفيذ",
        "l2_cta_caption":    "المستوى 2 يحوّل هذه النتائج إلى دفتر قواعد شخصي لصفقاتك الثلاثين القادمة — من بياناتك فقط. انضم إلى قائمة الانتظار؛ الأوائل يحصلون على الوصول أولاً.",
        "l2_cta_btn":        "الانضمام إلى قائمة انتظار المستوى 2",
        "l2_cta_done":       "تم تسجيلك في قائمة انتظار المستوى 2. سنتواصل معك عبر البريد.",
        "beta_email_bound":  "هذا البريد مرتبط برمز دعوة آخر. كل بريد يُستخدم مع رمز واحد فقط.",
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
    "EDGE_BELOW_BREAKEVEN": {
        "en": {"title": "Edge Below Breakeven",       "body_key": "message"},
        "fa": {"title": "کمی زیر سطح سر‌به‌سر",       "body_key": "body_fa"},
        "ar": {"title": "أداء دون نقطة التعادل بقليل",
               "body": "استراتيجيتك حالياً دون نقطة التعادل بقليل. قبل تحسين الفلاتر الجزئية، تحقق من أن جوهر الاستراتيجية يملك أفضلية كافية بعد التكاليف."},
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
    "EDGE_BELOW_BREAKEVEN": {
        "fa": "قبل از تنظیم سشن/نماد، ثابت کن هسته استراتژی بعد از هزینه‌ها (اسپرد/کمیسیون) edge دارد.",
        "ar": "قبل ضبط الجلسات/الرموز، تحقق من أفضلية الاستراتيجية بعد التكاليف (السبريد/العمولة).",
    },
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


# ── سیستم آیکون وکتوری (جایگزین ایموجی) ──────────────────────────────────────
ICON_PATHS = {
    "mail":   '<rect x="3" y="5" width="18" height="14" rx="2"/><polyline points="3 7 12 13 21 7"/>',
    "key":    '<circle cx="8" cy="15" r="4"/><path d="M10.9 12.1 21 2m-3 3 3 3"/>',
    "radar":  '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12 18.5 5.5"/>',
    "cube":   '<path d="M12 2 21 7v10l-9 5-9-5V7z"/><path d="M3 7l9 5 9-5M12 22V12"/>',
    "shield": '<path d="M12 2 20 6v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z"/>',
    "pulse":  '<polyline points="2 12 7 12 10 5 14 19 17 12 22 12"/>',
    "upload": '<path d="M12 16V4m0 0 5 5m-5-5L7 9"/><path d="M4 20h16"/>',
}


def bz_icon(name: str, size: int = 20, color: str = "#00E5A0") -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="1.6" stroke-linecap="round" '
            f'stroke-linejoin="round" style="vertical-align:middle;flex-shrink:0">'
            f'{ICON_PATHS.get(name, ICON_PATHS["pulse"])}</svg>')


def bz_section(num: str, icon_name: str, title: str) -> None:
    """هدر بخش با شماره مونواسپیس + آیکون وکتوری — سبک دیزاین‌سیستم."""
    st.markdown(
        f'<div class="bz-sec"><span class="bz-sec-num">{num} /</span>'
        f'{bz_icon(icon_name)}<span class="bz-sec-title">{safe(title)}</span></div>',
        unsafe_allow_html=True)


BZ_LOGO = (
    '<div class="bz-logo">'
    '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#00E5A0" '
    'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 2 21 7v10l-9 5-9-5V7z"/>'
    '<path d="M8.5 14.5v-4M12 16V8.5M15.5 13.5v-5" stroke="#EDF2F7" stroke-width="1.8"/>'
    '</svg>'
    '<span class="bz-logo-text">BAZAR<span>·AUDIT</span></span></div>')


def translate_warning(warning: str, lang: str) -> str:
    if "pnl_R not found" in warning:
        return T[lang]["r_warning"]
    return warning


# ── v2.1: نمره بازار + کارت بازیابی + نوار سفر ─────────────────────────────

def compute_bazar_score(result: dict):
    """نمره ۰-۱۰۰ با فرمول شفاف — فقط از متریک‌های واقعی موتور:
    Edge 40 (expectancy_R از −0.3 تا +0.3) + Consistency 20 (PF از 0.8 تا 1.5)
    + Discipline 25 (منهای ۱۰ برای هر یافته HIGH و ۵ برای هر MEDIUM —
    مشاهده‌ها کم نمی‌کنند چون شواهدشان کافی نیست) + Data 15 (تعداد معامله تا ۳۰۰)."""
    m = result.get("core_metrics", {}) or {}
    insights = result.get("insights", [])
    n = int(result.get("total_trades", 0) or 0)

    def _clamp(x):
        return max(0.0, min(1.0, x))

    expr = m.get("expectancy_R")
    if expr is None:
        # بدون R: تقریب از PF
        expr = (float(m.get("profit_factor") or 0) - 1.0) * 0.3
    edge = _clamp((float(expr) + 0.3) / 0.6) * 40

    pf = float(m.get("profit_factor") or 0)
    consistency = _clamp((pf - 0.8) / 0.7) * 20

    discipline = 25.0
    for ins in insights:
        if (ins.get("metric_snapshot") or {}).get("observation"):
            continue
        if str(ins.get("insight_id", "")).startswith("SAMPLE_SIZE"):
            continue
        sev = ins.get("severity")
        if sev == "HIGH":
            discipline -= 10
        elif sev == "MEDIUM":
            discipline -= 5
    discipline = max(0.0, discipline)

    data_score = _clamp(n / 300.0) * 15
    total = int(round(edge + consistency + discipline + data_score))
    return total, {"edge": round(edge, 1), "consistency": round(consistency, 1),
                   "discipline": round(discipline, 1), "data": round(data_score, 1)}


def biggest_recoverable(insights):
    """بزرگ‌ترین بهبود گذشته‌نگر از counterfactual یافته‌های معنادار (نه مشاهده‌ها)."""
    best = None
    for ins in insights:
        snap = ins.get("metric_snapshot") or {}
        if snap.get("observation"):
            continue
        cf = snap.get("counterfactual")
        if not isinstance(cf, dict):
            continue
        try:
            delta = float(cf.get("net_pnl_without_segment")) - float(cf.get("current_net_pnl"))
        except (TypeError, ValueError):
            continue
        if delta > 0 and (best is None or delta > best[0]):
            best = (delta, ins.get("insight_id", ""))
    return best


def _score_color(score: int) -> str:
    return "#00E5A0" if score >= 70 else ("#FFB020" if score >= 40 else "#FF4757")


def score_panel_html(score: int, parts: dict, recov, tx: dict) -> str:
    """پنل نمره + کارت بازیابی — هم در اپ هم در گزارش HTML."""
    c = _score_color(score)
    recov_html = ""
    if recov:
        recov_html = (
            f'<div style="background:#0D1117;border:1px solid #1C2530;border-top:2px solid #FFB020;'
            f'border-radius:6px;padding:14px 20px;min-width:230px;flex:1">'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:1.5px;'
            f'color:#5B6B7C;text-transform:uppercase">{safe(tx["recov_label"])}</div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:30px;font-weight:700;'
            f'color:#FFB020;margin-top:4px">+{recov[0]:,.0f}$</div>'
            f'<div style="font-size:11.5px;color:#5B6B7C;line-height:1.6;margin-top:6px">'
            f'{safe(tx["recov_note"])}</div></div>')
    return (
        f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin:6px 0 16px 0">'
        f'<div style="background:#0D1117;border:1px solid #1C2530;border-top:2px solid {c};'
        f'border-radius:6px;padding:14px 20px;min-width:200px">'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:1.5px;'
        f'color:#5B6B7C;text-transform:uppercase">{safe(tx["score_label"])}</div>'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:44px;font-weight:700;'
        f'color:{c};line-height:1.1">{score}<span style="font-size:16px;color:#5B6B7C"> /100</span></div>'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:9.5px;color:#5B6B7C;margin-top:4px">'
        f'EDGE {parts["edge"]} · CONSIST {parts["consistency"]} · DISCIPLINE {parts["discipline"]} · DATA {parts["data"]}</div>'
        f'<div style="font-size:11px;color:#5B6B7C;line-height:1.6;margin-top:6px">{safe(tx["score_caption"])}</div>'
        f'</div>{recov_html}</div>')


def journey_html(tx: dict) -> str:
    """نوار سفر سه‌مرحله‌ای — کاربر وسط مسیر است، نه آخرش."""
    def step(label, state):
        if state == "active":
            bc, tc = "#00E5A0", "#EDF2F7"
            badge = (f'<span style="color:#06140E;background:#00E5A0;border-radius:3px;'
                     f'padding:1px 7px;font-size:9px;font-weight:700;letter-spacing:1px">'
                     f'{safe(tx["journey_you"])}</span>')
        else:
            bc, tc = "#1C2530", "#5B6B7C"
            badge = (f'<span style="color:#5B6B7C;border:1px solid #1C2530;border-radius:3px;'
                     f'padding:1px 7px;font-size:9px;letter-spacing:1px">'
                     f'{safe(tx["journey_locked"])}</span>')
        return (f'<div style="flex:1;min-width:150px;background:#0D1117;border:1px solid {bc};'
                f'border-radius:6px;padding:11px 14px">'
                f'<div style="font-size:12.5px;font-weight:700;color:{tc};margin-bottom:5px">{safe(label)}</div>{badge}</div>')
    return (
        f'<div style="margin:18px 0 6px 0">'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:2px;'
        f'color:#5B6B7C;text-transform:uppercase;margin-bottom:8px">{safe(tx["journey_title"])}</div>'
        f'<div style="display:flex;gap:10px;flex-wrap:wrap">'
        f'{step(tx["journey_1"], "active")}{step(tx["journey_2"], "locked")}{step(tx["journey_3"], "locked")}'
        f'</div></div>')


# v2.0: متن‌های عمومی حالت observation (برای عربی که body استاتیک دارد + action فارسی/عربی)
OBS_BODY_AR = {
    "SESSION_TOXICITY": "في بياناتك الحالية تبدو إحدى الجلسات ضعيفة، لكن الأدلة لا تكفي بعد لحكم قاطع. مع المزيد من الصفقات تتحسن قوة الحكم.",
    "SYMBOL_NO_EDGE":   "في بياناتك الحالية يبدو أحد الرموز ضعيفاً، لكن الأدلة لا تكفي بعد لحكم قاطع. سجّل المزيد من الصفقات.",
    "TRADE_COUNT_CLIFF": "يبدو أن نسبة الفوز تنخفض بعد صفقة معينة، لكن الأدلة لا تكفي بعد. سجّل المزيد من أيام التداول.",
    "PAYOFF_IMBALANCE": "متوسط ربحك أصغر قليلاً من متوسط خسارتك؛ الفرق صغير وقد يكون ضوضاء. يُعاد الفحص مع بيانات أكثر.",
    "EDGE_BELOW_BREAKEVEN": "استراتيجيتك دون نقطة التعادل بقليل في هذه العينة، والفارق ضمن نطاق الضوضاء. تحقق من التكاليف وسجّل المزيد.",
}
OBS_ACTION = {
    "fa": "فعلاً تصمیم قطعی نگیر؛ ثبت معاملات را ادامه بده تا شواهد کافی شود.",
    "ar": "لا تتخذ قراراً نهائياً بعد؛ واصل تسجيل الصفقات حتى تكفي الأدلة.",
}


def get_insight_text(ins: dict, lang: str) -> tuple:
    iid = ins.get("insight_id", "")
    t   = INSIGHT_T.get(iid, {}).get(lang, {})
    obs = bool((ins.get("metric_snapshot") or {}).get("observation"))

    if lang == "en":
        title = t.get("title") or ins.get("insight_id", "")
        if obs:
            title = f"Observation: {title}"
    elif lang == "fa":
        title = ins.get("title_fa") or t.get("title") or iid
    else:
        title = t.get("title") or iid
        if obs:
            title = f"ملاحظة: {title}"

    if "body" in t:
        body = t["body"]
        if obs and lang == "ar":
            # v2.0: body استاتیک عربی قطعی است؛ در حالت مشاهده نسخه محتاط جایگزین می‌شود
            body = OBS_BODY_AR.get(iid, body)
    elif t.get("body_key") == "message" or lang == "en":
        # v1.5: در حالت انگلیسی هرگز به body_fa سقوط نکن (باگ قاطی‌شدن زبان‌ها)
        body = ins.get("message", "")
    else:
        body = ins.get("body_fa") or ins.get("message", "")

    action = ins.get("recommended_action", "")
    if lang in {"fa", "ar"}:
        if obs:
            # v2.0: در حالت مشاهده، توصیه قطعی استاتیک override نمی‌شود
            action = OBS_ACTION.get(lang, action)
        else:
            action = ACTION_T.get(iid, {}).get(lang, action)

    return title, body, action


# ── گزارش HTML تک‌کلیکی برای کاربر نهایی (v1.3) ──────────────────────────────
_REPORT_CSS = """ {EXTRAS_CSS} """.replace("{EXTRAS_CSS}", EXTRAS_CSS) + """
body{background:#07090C;color:#C9D4DF;font-family:'Vazirmatn','Inter',sans-serif;
     margin:0;padding:40px 6%;line-height:1.7}
.mono{font-family:'JetBrains Mono',monospace}
.kicker{font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:4px;color:#00E5A0}
h1{color:#EDF2F7;font-size:30px;margin:6px 0 2px 0}
.sub{color:#5B6B7C;font-size:13px;margin-bottom:22px}
.srcline{font-family:'JetBrains Mono',monospace;font-size:12px;letter-spacing:1px;
         border:1px solid #1C2530;border-radius:6px;padding:9px 14px;margin:14px 0;display:inline-block}
.grid{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}
.mc{background:#0D1117;border:1px solid #1C2530;border-top:2px solid #00E5A0;
    border-radius:6px;padding:12px 18px;min-width:120px}
.ml{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:1px;color:#5B6B7C;text-transform:uppercase}
.mv{font-family:'JetBrains Mono',monospace;font-size:21px;font-weight:700;color:#EDF2F7;margin-top:3px}
h2{color:#EDF2F7;font-size:18px;border-bottom:1px solid #1C2530;padding-bottom:8px;margin-top:32px}
.card{background:#0D1117;border:1px solid #1C2530;border-inline-start:4px solid #00E5A0;
      border-radius:6px;padding:16px 20px;margin:12px 0}
.badge{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:700;letter-spacing:1px;
       border-radius:3px;padding:2px 8px;margin-inline-start:8px}
.ct{font-size:15px;font-weight:700;color:#EDF2F7}
.cb{font-size:13.5px;color:#C9D4DF;margin-top:6px}
.act{font-size:13px;color:#00E5A0;border-inline-start:2px solid #00E5A0;
     padding-inline-start:10px;margin-top:10px}
table.cf{border-collapse:collapse;margin-top:10px;font-family:'JetBrains Mono',monospace;font-size:12px}
table.cf th,table.cf td{border:1px solid #1C2530;padding:5px 12px;color:#C9D4DF}
table.cf th{color:#5B6B7C;font-size:10px;letter-spacing:1px}
.meta{font-family:'JetBrains Mono',monospace;font-size:10px;color:#5B6B7C;letter-spacing:1px}
.footer{margin-top:36px;border-top:1px solid #1C2530;padding-top:14px;
        font-family:'JetBrains Mono',monospace;font-size:10.5px;color:#5B6B7C;line-height:1.8}
@media print{body{background:#fff;color:#222}
  .mc,.card{background:#fff;border-color:#ccc}.mv,.ct,h1,h2{color:#111}}
"""


def build_report_html(result: dict, tx: dict, lang: str, trader_id: str, source: str) -> str:
    """گزارش کامل خودکفا برای کاربر نهایی — بدون نیاز به دانستن JSON."""
    # v2.1 psychological conversion layer
    _score_html   = bazar_score_html(result, lang)
    _recover_html = recoverable_card_html(result.get("insights", []), lang)
    _journey_html = journey_bar_html(lang)
    _cta_html     = cta_block_html(lang)
    m        = result.get("core_metrics", {}) or {}
    insights = result.get("insights", [])
    direction = "rtl" if lang in RTL_LANGS else "ltr"
    sev_color = {"HIGH": "#FF4757", "MEDIUM": "#FFB020", "LOW": "#00E5A0"}
    sev_bg    = {"HIGH": "#2A0E12", "MEDIUM": "#2A1F08", "LOW": "#07251C"}

    wr   = m.get("win_rate") or 0
    bwr  = m.get("breakeven_wr") or 0
    expr = m.get("expectancy_R")
    exp_str = f"{expr:.2f}R" if expr is not None else f"{m.get('expectancy_dollar', 0):.1f}$"
    high_n = sum(1 for i in insights if i.get("severity") == "HIGH")
    med_n  = sum(1 for i in insights if i.get("severity") == "MEDIUM")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if source == "upload":
        src_line, src_c = tx["src_upload_banner"], "#00E5A0"
    else:
        src_line, src_c = tx["src_sample_banner"], "#FFB020"
    src_line = src_line.format(name=trader_id, n=result.get("total_trades", 0))

    def mc(label, value):
        return (f'<div class="mc"><div class="ml">{safe(label)}</div>'
                f'<div class="mv">{safe(value)}</div></div>')

    cards = "".join([
        mc(tx["trades"], result.get("total_trades", 0)),
        mc(tx["win_rate"], f"{wr*100:.1f}%"),
        mc(tx["lbl_breakeven"], f"{bwr*100:.1f}%"),
        mc(tx["profit_factor"], m.get("profit_factor", "—")),
        mc(tx["expectancy"], exp_str),
        mc(tx["lbl_sev"], f"{high_n} / {med_n}"),
    ])

    ins_html, act_html = "", ""
    for idx, ins in enumerate(insights, 1):
        sev = ins.get("severity", "LOW")
        c, bg = sev_color.get(sev, "#00E5A0"), sev_bg.get(sev, "#07251C")
        title, body, action = get_insight_text(ins, lang)
        cf = (ins.get("metric_snapshot") or {}).get("counterfactual")
        cf_html = ""
        if isinstance(cf, dict):
            cf_html = (
                f'<table class="cf"><tr><th></th><th>{safe(tx["cf_current"])}</th><th>{safe(tx["cf_without"])}</th></tr>'
                f'<tr><td>PF</td><td>{safe(cf.get("current_pf", "—"))}</td>'
                f'<td>{safe(cf.get("pf_without_segment", "—"))}</td></tr>'
                f'<tr><td>NET PNL</td><td>{safe(cf.get("current_net_pnl", "—"))}$</td>'
                f'<td>{safe(cf.get("net_pnl_without_segment", "—"))}$</td></tr></table>')
        ins_html += (
            f'<div class="card" style="border-inline-start-color:{c}">'
            f'<span class="ct">{safe(title)}</span>'
            f'<span class="badge" style="background:{bg};color:{c};border:1px solid {c}55">{sev}</span>'
            f'<span class="meta"> · {safe(ins.get("insight_id", ""))} · '
            f'{safe(tx["insight_meta_conf"])}:{safe(ins.get("confidence", ""))} · '
            f'n={safe(ins.get("sample_size", ""))}</span>'
            f'<div class="cb">{safe(body)}</div>{cf_html}'
            + (f'<div class="act">{safe(action)}</div>' if action else "")
            + '</div>')
        if action:
            act_html += (f'<div class="card"><span class="mono" style="color:#00E5A0">{idx:02d}</span>'
                         f' &nbsp;{safe(action)}</div>')

    if not ins_html:
        ins_html = f'<div class="card">{safe(tx["no_issues"])}</div>'
    if not act_html:
        act_html = '<div class="card">—</div>'

    warn_html = ""
    for w in result.get("warnings", []):
        warn_html += (f'<div class="card" style="border-inline-start-color:#FFB020">'
                      f'{safe(translate_warning(w, lang))}</div>')

    return f"""<!DOCTYPE html>
<html dir="{direction}" lang="{lang}">
<head>
<meta charset="utf-8">
<title>Bazar Audit — {safe(trader_id)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=JetBrains+Mono:wght@400;700&family=Vazirmatn:wght@400;700&display=swap" rel="stylesheet">
<style>{_REPORT_CSS}</style>
</head>
<body>
<div class="kicker">BAZAR AUDIT — {APP_VERSION.upper()}</div>
<h1>{safe(tx["title"])}</h1>
<div class="sub">{safe(tx["subtitle"])}<br>
<span class="mono">{safe(tx["report_generated"])}: {now}</span></div>
<div class="srcline" style="color:{src_c};border-color:{src_c}55">{safe(src_line)}</div>
<h2>{safe(tx["health_summary"])}</h2>
{_score_html}
{_recover_html}
<div class="grid">{cards}</div>
{warn_html}
<h2>{safe(tx["insights_header"])} — {len(insights)}</h2>
{ins_html}
<h2>{safe(tx["report_actions"])}</h2>
{act_html}
{_journey_html}
{_cta_html}
<div class="footer">{safe(tx["disclaimer"])}<br>BAZAR·AUDIT — v2.1</div>
</body></html>"""


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


def get_invite_codes() -> list:
    """لیست مرتب کدهای دعوت: از st.secrets[INVITE_CODES] (جداشده با کاما) یا لیست پیش‌فرض."""
    try:
        if "INVITE_CODES" in st.secrets:
            raw = str(st.secrets["INVITE_CODES"])
            return [c.strip() for c in raw.split(",") if c.strip()]
    except Exception:
        pass
    return list(DEFAULT_INVITE_CODES)


def load_assignments() -> dict:
    """نگاشت email → کد دعوت اختصاص‌یافته."""
    try:
        with open(ASSIGN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_assignments(data: dict) -> None:
    try:
        with open(ASSIGN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def assign_code_for_email(email: str):
    """v1.2: خروجی (status, code) — status یکی از new / exists / full.
    برای ایمیل تکراری کد لو نمی‌رود (جلوگیری از برداشت کد دیگران با دانستن ایمیل)."""
    em = email.strip().lower()
    assignments = load_assignments()
    if em in assignments and isinstance(assignments[em], dict):
        return "exists", None
    taken = {v["code"] for v in assignments.values() if isinstance(v, dict)}
    for code in get_invite_codes():
        if code not in taken:
            assignments[em] = {
                "code": code,
                "assigned_at": datetime.now(timezone.utc).isoformat(),
            }
            save_assignments(assignments)
            return "new", code
    # ظرفیت تکمیل → ایمیل در لیست انتظار ثبت می‌شود تا برای دسترسی پولی تماس بگیریم.
    wl = assignments.get("_waitlist", [])
    if not isinstance(wl, list):
        wl = []
    if em not in wl:
        wl.append(em)
        assignments["_waitlist"] = wl
        save_assignments(assignments)
    return "full", None


def _client_ip() -> str:
    """IP کلاینت از هدرها (روی Streamlit Cloud: X-Forwarded-For). لوکال = local."""
    try:
        h = st.context.headers
        return str(h.get("X-Forwarded-For", h.get("Origin", "local"))).split(",")[0].strip()
    except Exception:
        return "unknown"


def log_access(event: str, email: str = "", detail: str = "") -> None:
    """ثبت رخدادهای امنیتی: درخواست کد، تلاش ورود، آپلود — برای بررسی ورود غیرمجاز."""
    try:
        try:
            with open(ACCESS_LOG_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
            if not isinstance(log, list):
                log = []
        except Exception:
            log = []
        raw_ip = _client_ip()
        ip_val = raw_ip if raw_ip in ("local", "unknown") else hashlib.sha256(raw_ip.encode()).hexdigest()[:16]
        log.append({
            "ts":      datetime.now(timezone.utc).isoformat(),
            "event":   event,
            "email":   email.strip().lower(),
            "detail":  detail,
            "ip_hash": ip_val,  # فقط برای abuse detection — IP خام ذخیره نمی‌شود
        })
        with open(ACCESS_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log[-1000:], f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def email_hash(email: str) -> str:
    """sha256 از ایمیل trim+lowercase شده — ایمیل خام هیچ‌جا ذخیره نمی‌شود."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def get_token_activation(code: str):
    """v1.4: زمان اولین فعال‌سازی توکن (یا None اگر هنوز فعال نشده)."""
    acts = load_assignments().get("_activations", {})
    return acts.get(code) if isinstance(acts, dict) else None


def activate_token(code: str) -> None:
    """v1.4: ثبت اولین فعال‌سازی — فقط بار اول نوشته می‌شود."""
    data = load_assignments()
    acts = data.get("_activations")
    if not isinstance(acts, dict):
        acts = {}
    if code not in acts:
        acts[code] = datetime.now(timezone.utc).isoformat()
        data["_activations"] = acts
        save_assignments(data)


def token_expired(code: str) -> bool:
    """v1.4: توکن فعال‌شده‌ای که از پنجره ۲۴ ساعته خارج شده = سوخته."""
    act = get_token_activation(code)
    if not act:
        return False
    try:
        t0 = datetime.fromisoformat(act)
        return (datetime.now(timezone.utc) - t0).total_seconds() > TOKEN_TTL_HOURS * 3600
    except Exception:
        return False


def email_for_code(code: str):
    """v1.5: ایمیل ثبت‌نامی متصل به این کد دعوت (None اگر کد دستی توزیع شده)."""
    for em, rec in load_assignments().items():
        if isinstance(rec, dict) and rec.get("code") == code:
            return em
    return None


def email_bound_elsewhere(eh: str, code: str, usage: dict) -> bool:
    """v1.3: هر ایمیل فقط با یک کد دعوت — استفاده با کد دوم block می‌شود."""
    for c, rec in usage.items():
        if c != code and isinstance(rec, dict) and eh in rec.get("emails", []):
            return True
    return False


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

from bazar_report_extras import (
    bazar_score_html, recoverable_card_html,
    journey_bar_html, cta_block_html, EXTRAS_CSS
)

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
.stMetric, .stExpander, .stTabs { direction: rtl; text-align: right; font-family: 'Vazirmatn','Inter',sans-serif; }
div[data-testid="metric-container"] > div { text-align: right; }
.language-switcher, .language-switcher * { direction: ltr; text-align: left; }
.hero-title, .hero-sub { font-family: 'Vazirmatn','Inter',sans-serif; }
.disclaimer { border-left: 0 !important; border-right: 2px solid #1C2530; padding-left: 0 !important; padding-right: 10px; }
.sample-narrative { border-left: 1px solid #1C2530 !important; border-right: 3px solid #1C2530; }
.sample-narrative.good { border-right-color: #00E5A0; }
.sample-narrative.average { border-right-color: #FFB020; }
.sample-narrative.problem { border-right-color: #FF4757; }
.ins-card { border-left-width: 1px !important; }
.ins-card.HIGH { border-right: 4px solid #FF4757; }
.ins-card.MEDIUM { border-right: 4px solid #FFB020; }
.ins-card.LOW { border-right: 4px solid #00E5A0; }
.ins-action { border-left: 0 !important; border-right: 2px solid #00E5A0; padding-left: 0 !important; padding-right: 10px; }
</style>""", unsafe_allow_html=True)
    else:
        st.markdown("""
<style>
html, body, [class*="css"] { direction: ltr; text-align: left; }
.language-switcher, .language-switcher * { direction: ltr; text-align: left; }
</style>""", unsafe_allow_html=True)

# ── Base CSS — Quant Terminal Theme (v1.1) ───────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&family=Vazirmatn:wght@400;500;700;800&display=swap');

  :root {
    --bz-bg:     #07090C;
    --bz-panel:  #0D1117;
    --bz-border: #1C2530;
    --bz-text:   #C9D4DF;
    --bz-bright: #EDF2F7;
    --bz-dim:    #5B6B7C;
    --bz-green:  #00E5A0;
    --bz-red:    #FF4757;
    --bz-amber:  #FFB020;
  }

  html, body, [class*="css"] { font-family: 'Inter', 'Vazirmatn', sans-serif; }
  .stApp { background: var(--bz-bg); }

  /* ── Hero: ترمینال ── */
  .hero-kicker {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem; letter-spacing: 4px;
    color: var(--bz-green); margin-bottom: 6px;
  }
  .hero-title {
    font-size: 2.7rem; font-weight: 800; line-height: 1.15;
    color: var(--bz-bright); margin-bottom: 0.25rem;
  }
  .hero-title::after {
    content: '_'; color: var(--bz-green);
    animation: bz-blink 1.1s steps(1) infinite;
  }
  @keyframes bz-blink { 50% { opacity: 0; } }
  .hero-sub  { font-size: 1.05rem; color: var(--bz-dim); margin-bottom: 1.4rem; }

  .disclaimer {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem; color: var(--bz-dim);
    border-left: 2px solid var(--bz-border); padding-left: 10px;
    margin-bottom: 1.4rem; line-height: 1.7;
  }

  /* ── کارت‌های پروفایل نمونه ── */
  .sample-narrative {
    background: var(--bz-panel); border: 1px solid var(--bz-border);
    border-radius: 6px; padding: 13px 16px; margin-top: 6px;
    font-size: 0.86rem; color: var(--bz-text); line-height: 1.65;
    border-left: 3px solid var(--bz-border);
  }
  .sample-narrative.good    { border-left-color: var(--bz-green); }
  .sample-narrative.average { border-left-color: var(--bz-amber); }
  .sample-narrative.problem { border-left-color: var(--bz-red); }

  /* ── متریک‌ها: اعداد مونواسپیس ترمینالی ── */
  div[data-testid="metric-container"], div[data-testid="stMetric"] {
    background: var(--bz-panel); border: 1px solid var(--bz-border);
    border-top: 2px solid var(--bz-green);
    border-radius: 6px; padding: 13px 15px;
  }
  [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    color: var(--bz-bright);
  }
  [data-testid="stMetricLabel"] {
    color: var(--bz-dim) !important;
    letter-spacing: 0.5px; text-transform: uppercase; font-size: 0.72rem;
  }

  /* ── کارت insight ── */
  .ins-card {
    border-radius: 6px; padding: 16px 20px;
    margin-bottom: 13px; border: 1px solid var(--bz-border);
    background: var(--bz-panel);
  }
  .ins-card.HIGH   { border-left: 4px solid var(--bz-red);   box-shadow: -6px 0 18px -10px rgba(255,71,87,.5); }
  .ins-card.MEDIUM { border-left: 4px solid var(--bz-amber); }
  .ins-card.LOW    { border-left: 4px solid var(--bz-green); }
  .ins-title { font-size: 1.03rem; font-weight: 700; color: var(--bz-bright); margin-bottom: 4px; }
  .ins-body  { font-size: 0.9rem; color: var(--bz-text); line-height: 1.7; }
  .ins-action {
    font-size: 0.85rem; color: var(--bz-green);
    border-left: 2px solid var(--bz-green); padding-left: 10px; margin-top: 10px;
  }
  .ins-badge {
    display:inline-block; border-radius:3px; padding:2px 9px;
    font-family:'JetBrains Mono',monospace;
    font-size:0.68rem; font-weight:700; letter-spacing:1px;
    margin-right:6px; vertical-align:middle;
  }
  .badge-HIGH   { background:#2A0E12; color:#FF6B7A; border:1px solid #4A1820; }
  .badge-MEDIUM { background:#2A1F08; color:#FFC04D; border:1px solid #4A3812; }
  .badge-LOW    { background:#07251C; color:#4DEFB8; border:1px solid #0E4534; }

  /* ── دکمه‌ها و ورودی‌ها ── */
  .stButton > button {
    background: var(--bz-panel); border: 1px solid var(--bz-border);
    color: var(--bz-text); border-radius: 6px; font-weight: 600;
    transition: all .15s ease;
  }
  .stButton > button:hover {
    border-color: var(--bz-green); color: var(--bz-green);
    box-shadow: 0 0 14px rgba(0,229,160,.18);
  }
  .stTextInput input {
    background: var(--bz-panel) !important;
    border: 1px solid var(--bz-border) !important;
    border-radius: 6px !important; color: var(--bz-bright) !important;
    font-family: 'JetBrains Mono', monospace;
  }
  .stTextInput input:focus { border-color: var(--bz-green) !important;
    box-shadow: 0 0 0 1px var(--bz-green) !important; }

  /* ── تب‌ها ── */
  .stTabs [data-baseweb="tab"] {
    font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
    color: var(--bz-dim);
  }
  .stTabs [aria-selected="true"] { color: var(--bz-green) !important; }
  .stTabs [data-baseweb="tab-highlight"] { background-color: var(--bz-green); }

  /* ── جدول/اکسپندر/سایدبار ── */
  .stExpander { background: var(--bz-panel); border: 1px solid var(--bz-border); border-radius: 6px; }
  section[data-testid="stSidebar"] {
    background: #05070A; border-right: 1px solid var(--bz-border);
  }
  .language-switcher { margin: 0 0 18px 0; max-width: 520px; }
  hr { border-color: var(--bz-border) !important; }

  /* ── دیزاین‌سیستم: هدر بخش، لوگو، چیپ، نوار وضعیت ── */
  .bz-sec {
    display:flex; align-items:center; gap:10px;
    margin:14px 0 4px 0; padding-bottom:9px;
    border-bottom:1px solid var(--bz-border);
  }
  .bz-sec-num {
    font-family:'JetBrains Mono',monospace; font-size:.68rem;
    color:var(--bz-dim); letter-spacing:2px;
  }
  .bz-sec-title { font-size:1.12rem; font-weight:700; color:var(--bz-bright); }
  .bz-logo { display:flex; align-items:center; gap:10px; }
  .bz-logo-text {
    font-family:'JetBrains Mono',monospace; font-weight:700;
    font-size:1.02rem; letter-spacing:3px; color:var(--bz-bright);
  }
  .bz-logo-text span { color:var(--bz-green); }
  .bz-chip {
    display:inline-block; font-family:'JetBrains Mono',monospace;
    font-size:.62rem; letter-spacing:1.5px; color:var(--bz-green);
    border:1px solid #0E4534; background:#07251C;
    border-radius:3px; padding:2px 9px;
  }
  .bz-status {
    font-family:'JetBrains Mono',monospace; font-size:.66rem;
    letter-spacing:1.5px; color:var(--bz-dim);
    border:1px solid var(--bz-border); background:var(--bz-panel);
    border-radius:6px; padding:9px 16px;
    display:flex; gap:22px; flex-wrap:wrap; margin-top:16px;
  }
  .bz-dot { color:var(--bz-green); animation: bz-blink 2s steps(1) infinite; }
  div[data-testid="stAlert"] { border:1px solid var(--bz-border); border-radius:6px; }
  .stButton > button[kind="primary"] {
    background:var(--bz-green); color:#06140E; border:none;
    font-weight:700; letter-spacing:.5px;
  }
  .stButton > button[kind="primary"]:hover {
    background:#3DF0B8; color:#06140E;
    box-shadow:0 0 20px rgba(0,229,160,.4);
  }
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
    st.markdown(BZ_LOGO, unsafe_allow_html=True)
    st.markdown(f'<div style="margin:10px 0 0 2px"><span class="bz-chip">{safe(tx["app_version"])}</span></div>',
                unsafe_allow_html=True)
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
    if st.session_state.get("is_admin"):
        with st.expander("ACCESS LOG — admin"):
            try:
                with open(ACCESS_LOG_FILE, "r", encoding="utf-8") as f:
                    st.json(json.load(f)[-20:])
            except Exception:
                st.caption("no log yet")
    st.divider()
    st.caption(tx["disclaimer"])

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown(f'<div class="hero-kicker">BAZAR AUDIT — {APP_VERSION.upper()} / PRIVATE BETA</div>', unsafe_allow_html=True)
st.markdown(f'<div class="hero-title">{safe(tx["title"])}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="hero-sub">{safe(tx["subtitle"])}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="disclaimer">{safe(tx["disclaimer"])}</div>', unsafe_allow_html=True)

# ── Sample Picker / Upload ────────────────────────────────────────────────────
# ── Access Gate (v1.1): بدون کد دسترسی، هیچ‌چیز باز نمی‌شود ─────────────────────
if not st.session_state.get("access_granted", False):
    # ── صحنه سه‌بعدی ورودی + باران ماتریکس (v1.4) ──────────────────────────
    components.html(HERO_3D, height=312)
    components.html(MATRIX_BG, height=292)

    _gl, _gc, _gr = st.columns([1, 6, 1])
    with _gc:
        # ── گام ۱: ثبت ایمیل و دریافت کد رایگان (۱۰ ظرفیت بتا) ────────────────
        bz_section("01", "mail", tx["req_header"])
        st.caption(tx["req_caption"])
        req_email = st.text_input(tx["beta_email_label"], key="req_email")
        if st.button(tx["req_btn"], key="req_submit", type="primary"):
            email_ok = bool(req_email) and "@" in req_email and "." in req_email.split("@")[-1]
            if not email_ok:
                st.warning(tx["beta_invalid_email"])
            else:
                status, assigned = assign_code_for_email(req_email)
                log_access("code_request", email=req_email, detail=status)
                if status == "full":
                    st.error(tx["req_full"])
                elif status == "exists":
                    # v1.2: به ایمیل تکراری کد لو نمی‌رود — هر کس ایمیل تو را بداند نباید کدت را بگیرد.
                    st.warning(tx["req_exists"])
                else:
                    st.success(tx["req_code_msg"])
                    st.code(assigned)
                    st.info(tx["req_use_hint"])

        # ── گام ۲: ورود با کد ──────────────────────────────────────────────────
        bz_section("02", "key", tx["access_title"])
        code_in = st.text_input(tx["access_label"], type="password", key="access_input")
        if st.button(tx["access_btn"], key="access_submit", type="primary"):
            entered = code_in.strip()
            _admin_code = get_access_code()
            is_admin  = bool(entered) and bool(_admin_code) and entered == _admin_code
            is_invite = bool(entered) and entered in get_invite_codes()
            # v1.4: توکن یکبارمصرف — بعد از اولین فعال‌سازی فقط در پنجره ۲۴ ساعته کار می‌کند
            if is_invite and token_expired(entered):
                log_access("unlock_expired", detail=entered)
                st.error(tx["code_expired"])
            elif is_admin or is_invite:
                if is_invite:
                    activate_token(entered)
                log_access("unlock_ok", detail=("admin" if is_admin else entered))
                st.session_state["access_granted"] = True
                st.session_state["is_admin"]      = is_admin
                st.session_state["invite_code"]   = entered
                st.rerun()
            else:
                log_access("unlock_fail", detail=entered[:16])
                st.error(tx["access_wrong"])

        st.markdown(
            '<div class="bz-status">'
            '<span><span class="bz-dot">●</span> SYSTEM ONLINE</span>'
            '<span>ENGINE v2.1</span>'
            '<span>3 SAMPLE PROFILES</span>'
            '<span>10 BETA SLOTS</span>'
            '</div>', unsafe_allow_html=True)
    st.stop()

if DEMO_MODE:
    # ── بنر زنده Matrix صفحه اصلی (v1.3) ─────────────────────────────────
    components.html(MATRIX_BG, height=292)

    # v1.5: وقتی فایل کاربر آپلود شده، دموها داخل یک باکس بسته جمع می‌شوند
    _has_upload = st.session_state.get("beta_df") is not None
    chosen = None
    if _has_upload:
        _demo_box = st.expander(tx["demo_expander"], expanded=False)
    else:
        bz_section("01", "pulse", tx["pick_profile"])
        st.caption(tx["pick_caption"])
        _demo_box = st.container()

    with _demo_box:
        col_g, col_a, col_p = st.columns(3)
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
    bz_section("02", "upload", tx["beta_header"])
    st.caption(tx["beta_privacy"])

    # وضعیت کد/سهمیه + v1.5: ایمیل آپلود قفل به ایمیل توکن
    _code     = st.session_state.get("invite_code", "")
    _is_admin = st.session_state.get("is_admin", False)
    _usage    = load_beta_usage()
    _used     = int(_usage.get(_code, {}).get("upload_count", 0))
    _expected_email = None if _is_admin else email_for_code(_code)

    col_e, col_u = st.columns([1, 2])
    with col_e:
        if _expected_email:
            beta_email = st.text_input(tx["beta_email_label"], value=_expected_email,
                                       disabled=True, key="beta_email")
        else:
            beta_email = st.text_input(tx["beta_email_label"], key="beta_email")
    with col_u:
        beta_file = st.file_uploader(tx["upload_label"], type=["csv"], key="beta_uploader")

    if "active_sample" not in st.session_state:
        st.session_state.active_sample = None
    if chosen:
        st.session_state.active_sample = chosen
        st.session_state["view"] = "sample"

    if not _is_admin:
        st.caption(tx["beta_quota_status"].format(used=_used, max=MAX_UPLOADS_PER_CODE))

    if beta_file is not None:
        email_ok = bool(beta_email) and "@" in beta_email and "." in beta_email.split("@")[-1]
        sig = (beta_file.name, beta_file.size, (beta_email or "").strip().lower())
        already_this_run = (
            st.session_state.get("last_upload_sig") == sig
            and st.session_state.get("beta_df") is not None
        )
        if already_this_run:
            pass  # همین فایل قبلاً در این سشن audit شده؛ سهمیه دوباره کم نمی‌شود.
        elif not email_ok:
            st.warning(tx["beta_invalid_email"])
        elif beta_file.size > MAX_UPLOAD_MB * 1024 * 1024:
            st.error(tx["beta_file_too_big"])
        elif not _is_admin and _used >= MAX_UPLOADS_PER_CODE:
            st.error(tx["beta_quota_used"].format(max=MAX_UPLOADS_PER_CODE))
            log_access("upload_blocked_quota", email=beta_email, detail=_code)
        elif not _is_admin and _expected_email and beta_email.strip().lower() != _expected_email:
            # v1.5: آپلود فقط با همان ایمیل صاحب توکن
            st.error(tx["beta_email_mismatch"])
            log_access("upload_blocked_mismatch", email=beta_email, detail=_code)
        elif (not _is_admin and not _expected_email
              and _usage.get(_code, {}).get("emails")
              and email_hash(beta_email) != _usage.get(_code, {}).get("emails", [None])[0]):
            # v1.5: کد دستی — اولین ایمیل استفاده‌شده صاحب کد می‌شود
            st.error(tx["beta_email_mismatch"])
            log_access("upload_blocked_mismatch", email=beta_email, detail=_code)
        elif not _is_admin and email_bound_elsewhere(email_hash(beta_email), _code, _usage):
            # v1.3: ایمیل تکراری با کد دیگر = block (جلوگیری از چرخاندن یک ایمیل بین کدها)
            st.error(tx["beta_email_bound"])
            log_access("upload_blocked_email", email=beta_email, detail=_code)
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
                    rec = _usage.get(_code, {"upload_count": 0,
                                             "first_upload_at": now,
                                             "emails": []})
                    rec["upload_count"] = int(rec.get("upload_count", 0)) + 1
                    rec["last_upload_at"] = now
                    eh = email_hash(beta_email)
                    if eh not in rec.get("emails", []):
                        rec.setdefault("emails", []).append(eh)
                    _usage[_code] = rec
                    save_beta_usage(_usage)
                    st.session_state["beta_df"] = bdf.sort_values('open_time').reset_index(drop=True)
                    st.session_state["beta_trader_id"] = beta_file.name.replace('.csv', '')
                    st.session_state["last_upload_sig"] = sig
                    st.session_state["view"] = "upload"
                    # رفع ابهام منبع: بعد از آپلود موفق، انتخاب دموی قبلی پاک می‌شود
                    st.session_state.active_sample = None
                    log_access("upload_ok", email=beta_email,
                               detail=f"{beta_file.name}|{len(bdf)} trades|code={_code}")

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
# v1.3: JSON فقط برای ادمین — کاربر نهایی نباید JSON ببیند
if st.session_state.get("is_admin"):
    tab_report, tab_data, tab_json = st.tabs([tx["tab_report"], tx["tab_data"], tx["tab_json"]])
else:
    tab_report, tab_data = st.tabs([tx["tab_report"], tx["tab_data"]])
    tab_json = None

# ════════════════════════════════════════════════════════════════════════════
with tab_report:

    # ── بنر منبع گزارش (رفع ابهام دمو/فایل کاربر — v1.2) ─────────────────────
    if source == "upload":
        _src_txt = tx["src_upload_banner"].format(name=trader_id, n=report.total_trades)
        _src_css = "background:#07251C;border:1px solid #0E4534;color:#4DEFB8;"
    else:
        _src_txt = tx["src_sample_banner"].format(name=trader_id, n=report.total_trades)
        _src_css = "background:#2A1F08;border:1px solid #4A3812;color:#FFC04D;"
    st.markdown(
        f'<div style="{_src_css}border-radius:6px;padding:10px 16px;margin-bottom:14px;'
        f'font-family:JetBrains Mono,monospace;font-size:.74rem;letter-spacing:1.5px;">'
        f'{safe(_src_txt)}</div>', unsafe_allow_html=True)

    # v1.2: اگر کاربر فایل آپلودشده دارد ولی روی دمو کلیک کرده، راه برگشت همیشه جلوی چشم باشد
    if source == "sample" and st.session_state.get("beta_df") is not None:
        if st.button(tx["back_to_upload"], key="back_to_upload_btn", type="primary"):
            st.session_state["view"] = "upload"
            st.rerun()

    # ── v1.3: گزارش کامل تک‌کلیکی برای کاربر نهایی (HTML خودکفا) ───────────────
    try:
        _full_report = build_report_html(result, tx, lang, trader_id, source)
        _dl1, _dl2 = st.columns([1, 2])
        with _dl1:
            st.download_button(
                label=tx["report_btn"],
                data=_full_report.encode("utf-8"),
                file_name=f"bazar_report_{trader_id}.html",
                mime="text/html",
                key="dl_full_report",
                type="primary",
            )
        with _dl2:
            st.caption(tx["report_hint"])
    except Exception:
        pass  # خروجی گزارش نباید هرگز صفحه را بشکند

    # narrative banner — فقط برای پروفایل‌های نمونه، نه آپلود کاربر
    if DEMO_MODE and source == "sample":
        key = st.session_state.active_sample
        narrative_map = {"good": tx["good_narrative"], "average": tx["avg_narrative"], "problem": tx["prob_narrative"]}
        color_map     = {"good": "#00E5A0", "average": "#FFB020", "problem": "#FF4757"}
        st.markdown(f"""
        <div style="background:#0D1117;border:1px solid #1C2530;border-left:4px solid {color_map[key]};
                    border-radius:8px;padding:14px 20px;margin-bottom:18px;
                    font-size:0.95rem;color:#e2e8f0;">
            <strong>{safe(tx['bazar_says'])}:</strong> {safe(narrative_map[key])}
        </div>
        """, unsafe_allow_html=True)

    bz_section("01", "shield", tx["health_summary"])

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
        bz_section("02", "radar", f"{tx['insights_header']} — {len(insights)}")
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

    # ── نقشه سه‌بعدی معاملات (v1.1) ────────────────────────────────────────────
    if HAS_PLOTLY and 'open_time' in df.columns and len(df) > 0:
        st.divider()
        bz_section("03", "cube", tx["viz3d_header"])
        st.caption(tx["viz3d_caption"])
        try:
            _p = df.copy()
            _p['hour'] = _p['open_time'].dt.hour + _p['open_time'].dt.minute / 60.0
            _p['day']  = (_p['open_time'] - _p['open_time'].min()).dt.days
            zcol = 'pnl_R' if ('pnl_R' in _p.columns and _p['pnl_R'].notna().all()) else 'pnl'
            _w = _p[_p['pnl'] > 0]
            _l = _p[_p['pnl'] <= 0]
            fig = go.Figure()
            for _grp, _name, _color in ((_w, 'WIN', '#00E5A0'), (_l, 'LOSS', '#FF4757')):
                fig.add_trace(go.Scatter3d(
                    x=_grp['hour'], y=_grp['day'], z=_grp[zcol],
                    mode='markers', name=_name,
                    marker=dict(size=4, color=_color, opacity=0.75,
                                line=dict(width=0)),
                    text=_grp['symbol'] if 'symbol' in _grp.columns else None,
                    hovertemplate='%{text}<br>hour=%{x:.1f} | day=%{y} | ' + zcol + '=%{z}<extra></extra>',
                ))
            _ax = dict(backgroundcolor='#0D1117', gridcolor='#1C2530',
                       zerolinecolor='#2A3A4A', color='#5B6B7C')
            fig.update_layout(
                template='plotly_dark',
                paper_bgcolor='#07090C',
                scene=dict(
                    xaxis=dict(title='HOUR', **_ax),
                    yaxis=dict(title='DAY',  **_ax),
                    zaxis=dict(title=zcol.upper(), **_ax),
                ),
                margin=dict(l=0, r=0, t=10, b=0), height=520,
                legend=dict(font=dict(family='JetBrains Mono', color='#C9D4DF'),
                            bgcolor='rgba(13,17,23,.7)'),
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass  # نمودار تزئینی است؛ هرگز نباید گزارش را بشکند.

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
if tab_json is not None:
    with tab_json:
        st.subheader(tx["json_title"])
        st.json(result)
        st.download_button(
            label=tx["json_download"],
            data=json.dumps(result, ensure_ascii=False, indent=2, default=str),
            file_name=f"bazar_audit_{trader_id}.json",
            mime="application/json",
        )
