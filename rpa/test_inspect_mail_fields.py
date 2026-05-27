from playwright.sync_api import sync_playwright
import time

GROUPWARE_URL = "http://gw.ramostek.com/"
MAIL_WRITE_URL = "http://gw.ramostek.com/ekp/view/eml/emlMailRegPopup?mode=write"

print("===== 메일 입력칸 정보 확인 시작 =====")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto(GROUPWARE_URL, wait_until="domcontentloaded", timeout=60000)

    print("로그인 후 Enter를 누르세요.")
    input()

    page.goto(MAIL_WRITE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    inputs = page.locator("input, textarea, select")
    count = inputs.count()

    print(f"입력 요소 개수: {count}")

    for i in range(count):
        item = inputs.nth(i)
        print("-----")
        print(f"index: {i}")
        print(f"tag: {item.evaluate('el => el.tagName')}")
        print(f"type: {item.get_attribute('type')}")
        print(f"name: {item.get_attribute('name')}")
        print(f"id: {item.get_attribute('id')}")
        print(f"placeholder: {item.get_attribute('placeholder')}")
        print(f"value: {item.input_value() if item.evaluate('el => el.tagName') != 'SELECT' else ''}")

    input("확인 후 Enter를 누르면 종료합니다...")
    browser.close()

print("===== 메일 입력칸 정보 확인 끝 =====")