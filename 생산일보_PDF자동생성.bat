@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ========================
echo Backend 실행
echo ========================

start "backend" /min cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

timeout /t 5

echo ========================
echo Frontend 실행
echo ========================

start "frontend" /min cmd /k "cd /d "%~dp0frontend" && npm run dev"

timeout /t 15

echo ========================
echo 생산일보 PDF 자동 생성
echo ========================

python rpa\test_download_pdf.py

if errorlevel 1 (
    echo PDF 자동화 실패
    pause
    exit /b
)

timeout /t 3

echo ========================
echo 그룹웨어 메일 자동 작성
echo ========================

python rpa\auto_write_mail_draft.py

if errorlevel 1 (
    echo 메일 자동화 실패
    pause
    exit /b
)

echo ========================
echo 전체 자동화 완료
echo ========================

pause