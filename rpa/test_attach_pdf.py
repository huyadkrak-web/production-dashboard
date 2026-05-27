from pathlib import Path
import pyautogui
import pyperclip
import time

download_dir = Path(r"C:\Users\USER\Downloads")

pdf_files = list(download_dir.glob("생산일보_*.pdf"))

print("===== PDF 첨부 테스트 시작 =====")

if not pdf_files:
    print("생산일보 PDF 파일을 찾지 못했습니다.")
    raise SystemExit

latest_pdf = max(pdf_files, key=lambda file: file.stat().st_mtime)

print(f"첨부할 PDF: {latest_pdf}")

print("5초 안에 그룹웨어 첨부 파일 선택창을 띄우세요.")
print("('내 PC' 클릭 후 파일 선택창 열린 상태)")

time.sleep(5)

# 파일 경로 복사
pyperclip.copy(str(latest_pdf))

# 붙여넣기
pyautogui.hotkey("ctrl", "v")

time.sleep(1)

# Enter
pyautogui.press("enter")

print("PDF 첨부 완료!")