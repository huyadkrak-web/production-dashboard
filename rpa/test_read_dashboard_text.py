from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    page.goto("http://localhost:5173")

    # 페이지 로딩 대기
    page.wait_for_timeout(5000)

    # 전체 텍스트 읽기
    full_text = page.locator("body").inner_text()

    print("===== 대시보드 텍스트 시작 =====")
    print(full_text)
    print("===== 대시보드 텍스트 끝 =====")

    time.sleep(10)

    browser.close()
    