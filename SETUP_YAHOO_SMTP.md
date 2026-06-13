# راه‌اندازی SMTP با Yahoo Mail

## یک کار داری — App Password یاهو

### مراحل (5 دقیقه):

1. برو به: https://account.yahoo.com/security
2. **"Two-step verification"** را فعال کن (اگر نیست)
3. پایین صفحه → **"Generate app password"** یا **"App passwords"**
4. از dropdown انتخاب کن: **Other app**
5. بنویس: `Bazar Audit`
6. دکمه **Generate** → یک کد 16 کاراکتری می‌گیری مثل: `abcd efgh ijkl mnop`

---

## بعد از گرفتن App Password:

### در `.streamlit/secrets.toml`:
```
SMTP_PASS = "abcdefghijklmnop"   # بدون فاصله بنویس
```

### در Streamlit Cloud:
Settings → Secrets → این 4 خط را اضافه کن:
```
SMTP_HOST = "smtp.mail.yahoo.com"
SMTP_PORT = "587"
SMTP_USER = "khosromahdavi71@yahoo.com"
SMTP_PASS = "abcdefghijklmnop"
SMTP_FROM = "Bazar Audit <khosromahdavi71@yahoo.com>"
```

---

## تست ایمیل:
بعد از وارد کردن App Password، در اپ یک ایمیل به خودت بفرست و چک کن رسید یا نه.
فاصله‌های کد را حذف کن — فقط 16 حرف پشت سر هم.
