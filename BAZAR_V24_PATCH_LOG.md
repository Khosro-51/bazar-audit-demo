# v2.4 Patch Log — 2026-06-13

## خلاصه
چهار مشکل گزارش‌شده توسط مهندس ارشد (review v2.2) قبل از ارسال به testers:

---

### 1. Bazar Score رنگ — amber هنگام expectancy منفی
**فایل:** `bazar_report_extras.py → bazar_score_html()`
```python
color = score_color(score) if exp_r >= 0 else ("#FFB020" if score >= 40 else "#FF4757")
```
- Score 70 سبز با PF=0.9 گمراه‌کننده بود → الان amber

---

### 2. کارت Observation — border و badge خاکستری
**فایل:** `streamlit_app.py` — insight loop (~line 944)
```python
is_obs = ins.get("observation", False)
c  = "#586069" if is_obs else sev_color.get(sev, "#00E5A0")
bg = "#1C2530" if is_obs else sev_bg.get(sev, "#07251C")
```
- Action div: `class="act-obs"` (CSS gray/italic) برای observations
- **CSS:** `.act-obs` به `EXTRAS_CSS` در `bazar_report_extras.py` اضافه شد

---

### 3. Action Plan — اقدام تحقیقی ۳۰-معامله‌ای
**فایل:** `bazar_insights.py`

| Insight | قبل | بعد |
|---|---|---|
| EDGE_BELOW_BREAKEVEN | "Track costs and collect more trades" | "Research action (next 30 trades): Log exact spread/commission..." |
| SESSION_TOXICITY | "No firm action yet — keep logging; judgment power..." | "Research action: Tag this session separately. Do not increase size/risk..." |
| TRADE_COUNT_CLIFF | "No firm action yet — keep logging; re-check..." | "Research action: Log trade sequence number (1st, 2nd, 3rd) per session..." |
| SYMBOL_NO_EDGE | "No firm action yet — keep logging trades on this symbol..." | "Research action: Keep trading but tag it. Record setup type per trade..." |

---

### 4. جدول WITHOUT → Historical What-if برای Observations
**فایل:** `streamlit_app.py`
- `cf_without_obs: "Historical What-if"` به EN tx dict اضافه شد
- Header logic:
```python
tx.get("cf_without_obs", tx["cf_without"]) if ins.get("observation") else tx["cf_without"]
```
- FA/AR: fallback به مقدار موجود `cf_without` در tx dict

---

### همچنین در این push (v2.3 که قبلاً نوشته شد):
- Equity curve SVG inline با watchlist markers (yellow circles)
- pnl_series injection از session_state قبل از build_report_html

---

### Push command:
```cmd
cd /d "C:\Users\Khosro\Desktop\web\Bazar Audit Engine v1"
"C:\Program Files\Git\cmd\git.exe" --git-dir=.codex-git-meta add .
"C:\Program Files\Git\cmd\git.exe" --git-dir=.codex-git-meta commit -m "v2.4: obs card gray, score amber for neg-expectancy, research actions, Historical What-if"
"C:\Program Files\Git\cmd\git.exe" --git-dir=.codex-git-meta push origin main
```

---

### نکات فنی:
- `ins.get("observation", False)` — اگر field وجود نداشت `False` → کارت سبز می‌ماند (finding)
- `is_obs` با `_extract_cf_items()` در bazar_report_extras هماهنگ است (هر دو observation field را چک می‌کنند)
- FA/AR `cf_without_obs` ترجمه اضافه نشد — fallback به `cf_without` ایمن است
- Score color: threshold `exp_r >= 0` نه `exp_r > 0` — اگر دقیقاً صفر باشد، رنگ normal می‌ماند
