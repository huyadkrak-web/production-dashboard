from pathlib import Path
from datetime import datetime, timedelta
import json
from playwright.sync_api import sync_playwright

GROUPWARE_URL = "http://gw.ramostek.com/"
MAIL_WRITE_URL = "http://gw.ramostek.com/ekp/view/eml/emlMailRegPopup?mode=write"

PROJECT_DIR = Path(r"C:\Users\USER\Desktop\생산일보프로그램")
TEMP_DIR = PROJECT_DIR / "rpa" / "temp"
DOWNLOAD_DIR = Path(r"C:\Users\USER\Downloads")

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


def make_mail_subject():
    return (
        f"CTST 3Camp 생산일보 "
        f"({REPORT_DATE.year % 100:02d}-{REPORT_DATE.month:02d}-{REPORT_DATE.day:02d})"
    )


def make_mail_body():
    values = load_mail_values()

    monthly_target = values.get("monthly_target", "확인필요")
    shipping_qty = values.get("shipping_qty", "확인필요")

    date_text = f"{REPORT_DATE.year % 100}년 {REPORT_DATE.month}월 {REPORT_DATE.day}일"
    month = REPORT_DATE.month

    return f"""안녕하세요 3Camp 한훈혜 입니다.

{date_text} 생산일보 전달 드립니다.

- {month}월 {PRODUCT_NAME}의 생산목표는 {monthly_target} 입니다.

- {month}월 출하 누적 수량 {shipping_qty} 입니다.

감사합니다."""


def find_latest_pdf():
    pdf_files = list(DOWNLOAD_DIR.glob("생산일보_*.pdf"))
    if not pdf_files:
        raise FileNotFoundError("생산일보 PDF 파일을 찾지 못했습니다.")
    return max(pdf_files, key=lambda file: file.stat().st_mtime)


print("===== 메일 직접 입력 테스트 시작 =====")

latest_pdf = find_latest_pdf()
print(f"첨부 PDF: {latest_pdf}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto(GROUPWARE_URL, wait_until="domcontentloaded", timeout=60000)

    print("그룹웨어 로그인 후 Enter를 누르세요.")
    input()

    page.goto(MAIL_WRITE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    inputs = page.locator("input, textarea, select")

    print("받는사람 입력")
    inputs.nth(15).fill(TO_RECIPIENTS)

    print("참조 입력")
    inputs.nth(18).fill(CC_RECIPIENTS)

    print("제목 입력")
    page.locator("#emlMailReg_subject").fill(make_mail_subject())

    print("PDF 첨부")
    page.locator("input[type='file']").set_input_files(str(latest_pdf))

    print("본문 hidden 값 입력")
    page.locator("#emlMailReg_content").evaluate(
        "(el, value) => { el.value = value; }",
        make_mail_body()
    )

    print("입력 완료. 화면에서 확인하세요.")
    input("확인 후 Enter를 누르면 종료합니다...")

    browser.close()

print("===== 메일 직접 입력 테스트 끝 =====")