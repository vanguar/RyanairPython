@echo off
setlocal
cd /d %~dp0
python tools\build_airports.py || py tools\build_airports.py || exit /b 1
git add data\airports_raw.json data\countries_data.json bot\airports_raw.json
git commit -m "airports update: %date% %time%"
git push
echo ✔ Готово
pause
