from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
import time

print("===== 기준일 선택 + 기준정보 불러오기 JS 클릭 테스트 시작 =====")

report_date = datetime.now() - timedelta(days=1)
date_text = report_date.strftime("%Y-%m-%d")

print(f"설정할 기준일: {date_text}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    page.goto("http://localhost:5173")
    page.wait_for_timeout(3000)

    date_input = page.locator("input[type='date']").first

    print("기준일 입력 중...")
    date_input.fill(date_text)

    page.wait_for_timeout(1000)

    load_button = page.get_by_role("button", name="불러오기").nth(0)

    print("기준정보 불러오기 JS 클릭")
    load_button.evaluate("button => button.click()")

    print("기준정보 불러오기 완료 확인 대기")
    time.sleep(10)

    browser.close()

print("===== 기준일 선택 + 기준정보 불러오기 JS 클릭 테스트 끝 =====")