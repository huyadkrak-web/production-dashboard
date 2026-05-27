import pyautogui
import pyperclip
import time
from datetime import datetime

from datetime import datetime, timedelta

report_date = datetime.now() - timedelta(days=1)

subject = (
    f"CTST 3Camp 생산일보 "
    f"({report_date.year % 100:02d}-{report_date.month:02d}-{report_date.day:02d})"
)

print("===== 메일 제목 자동 입력 테스트 =====")

print("5초 안에 메일 제목 입력칸을 클릭하세요.")

time.sleep(5)

pyperclip.copy(subject)

pyautogui.hotkey("ctrl", "v")

print("메일 제목 입력 완료!")
print(f"입력된 제목: {subject}")