from pathlib import Path
from datetime import datetime, timedelta
import time
import json
import pyautogui
import pyperclip

PROJECT_DIR = Path(r"C:\Users\USER\Desktop\생산일보프로그램")
TEMP_DIR = PROJECT_DIR / "rpa" / "temp"

MAIL_VALUES_PATH = TEMP_DIR / "mail_values.json"

TO_RECIPIENTS = (
    "tschang@ctst.co.kr; "
    "sjh@ctst.co.kr; "
    "ykjang@ctst.co.kr; "
    "msoh@ctst.co.kr; "
    "ktaejun@ctst.co.kr; "
    "ojs@ctst.co.kr; "
    "cge@ctst.co.kr"
)

CC_RECIPIENTS = "ws.sin@ctst.co.kr"

REPORT_DATE = datetime.now() - timedelta(days=1)

PRODUCT_NAME = "V6P 132FBGA-2Chip Stack"


def load_mail_values():
    if not MAIL_VALUES_PATH.exists():
        return {
            "monthly_target": "확인필요",
            "shipping_qty": "확인필요",
        }

    with open(MAIL_VALUES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def paste_text(text):
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")


def make_mail_subject():
    return (
        f"CTST 3Camp 생산일보 "
        f"({REPORT_DATE.year % 100:02d}-{REPORT_DATE.month:02d}-{REPORT_DATE.day:02d})"
    )


def make_mail_body():
    mail_values = load_mail_values()

    monthly_target = mail_values.get("monthly_target", "확인필요")
    shipping_qty = mail_values.get("shipping_qty", "확인필요")

    month = REPORT_DATE.month

    return f"""안녕하세요 3Camp 한훈혜 입니다.

- {month}월 {PRODUCT_NAME}의 생산목표는 {monthly_target} 입니다.

- {month}월 출하 누적 수량 {shipping_qty} 입니다.

감사합니다."""


print("===== 메일 TAB 자동 입력 테스트 시작 =====")

print("메일 작성창을 띄워두세요.")
print("받는사람 칸에 커서가 있는 상태로 5초 대기합니다.")

time.sleep(5)

# 받는사람
print("받는사람 입력")
paste_text(TO_RECIPIENTS)

pyautogui.press("tab")
time.sleep(1)

# 참조
print("참조 입력")
paste_text(CC_RECIPIENTS)

pyautogui.press("tab")
time.sleep(1)

# 제목
print("제목 입력")
paste_text(make_mail_subject())

# 본문 영역까지 이동
for _ in range(6):
    pyautogui.press("tab")
    time.sleep(0.3)

# 본문
print("본문 입력")
paste_text(make_mail_body())

print("===== 메일 TAB 자동 입력 테스트 끝 =====")