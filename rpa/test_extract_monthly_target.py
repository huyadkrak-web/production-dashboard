from playwright.sync_api import sync_playwright
import re
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    page.goto("http://localhost:5173")

    page.wait_for_timeout(5000)

    full_text = page.locator("body").inner_text()

    print("===== 월간플랜 목표 분석 시작 =====")

    # 예: 5월 목표 100K
    match = re.search(r"(\d{1,2})월 목표\s+([0-9,]+K)", full_text)

    if match:
        month = match.group(1)
        target = match.group(2)

        print(f"월: {month}월")
        print(f"생산목표: {target}")
        print(f"메일 표시용: {month}월 생산목표 {target}")

    else:
        print("월간플랜 목표를 찾지 못했습니다.")
        print("월간플랜 엑셀 업로드 후 다시 실행해 주세요.")

    print("===== 월간플랜 목표 분석 끝 =====")

    time.sleep(10)

    browser.close()
    