from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    page.goto("http://localhost:5173")

    print("대시보드 접속 성공")

    time.sleep(10)

    browser.close()
    