from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright
import time

WORK_DIR = Path(r"C:\Users\USER\Desktop\작업일보")
monthly_plan = WORK_DIR / "월간플랜.xlsx"

print("===== 월간플랜 파일 선택 테스트 시작 =====")

if not monthly_plan.exists():
    print(f"[ERROR] 월간플랜 파일 없음: {monthly_plan}")
    raise SystemExit

report_date = datetime.now() - timedelta(days=1)
date_text = report_date.strftime("%Y-%m-%d")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    page.goto("http://localhost:5173")
    page.wait_for_timeout(3000)

    print(f"기준일 입력: {date_text}")
    page.locator("input[type='date']").first.fill(date_text)

    print("기준정보 불러오기")
    load_button = page.get_by_role("button", name="불러오기").nth(0)
    load_button.evaluate("button => button.click()")

    page.wait_for_timeout(2000)

    print("월간플랜 파일 선택")
    file_inputs = page.locator("input[type='file']")
    file_inputs.nth(0).set_input_files(str(monthly_plan))

    print("월간플랜 파일 선택 완료")
    print("화면에서 월간플랜 파일명이 들어갔는지 확인하세요.")
    print("아직 생산일보 계산은 누르지 않았습니다.")

    time.sleep(15)
    browser.close()

print("===== 월간플랜 파일 선택 테스트 끝 =====")