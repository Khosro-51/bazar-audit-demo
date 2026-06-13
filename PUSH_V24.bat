@echo off
cd /d "C:\Users\Khosro\Desktop\web\Bazar Audit Engine v1"
echo Pushing v2.4 to GitHub...
"C:\Program Files\Git\cmd\git.exe" --git-dir=.codex-git-meta add .
"C:\Program Files\Git\cmd\git.exe" --git-dir=.codex-git-meta commit -m "v2.4: sidebar version fix, obs counter, gray obs cards, research actions, email delivery, terminal messages aligned to product, Yahoo SMTP configured"
"C:\Program Files\Git\cmd\git.exe" --git-dir=.codex-git-meta push origin main
echo.
echo Done! Check above for push status.
pause
