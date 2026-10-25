@echo off
chcp 65001 >nul
cd /d "C:\Users\interpol\Desktop\Фуд-контроль"

echo 📋 Проверка статуса git...
git status

echo.
echo 📝 Добавление всех файлов...
git add -A

echo.
echo 📤 Проверка что будет закоммичено...
git status

echo.
echo 💬 Коммит с сообщением...
git commit -m "Fix: добавить menu_pdf.py, исправить логику недель, добавить PyMuPDF"

echo.
echo 🚀 Пуш на GitHub...
git push origin main

echo.
echo ✅ Готово! Проверь Amvera - контейнер должен пересобраться автоматически
pause
