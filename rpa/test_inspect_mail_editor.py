from playwright.sync_api import sync_playwright

GROUPWARE_URL = "http://gw.ramostek.com/"
MAIL_WRITE_URL = "http://gw.ramostek.com/ekp/view/eml/emlMailRegPopup?mode=write"

print("===== 메일 본문 에디터 확인 시작 =====")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto(GROUPWARE_URL, wait_until="domcontentloaded", timeout=60000)

    print("그룹웨어 로그인 후 Enter를 누르세요.")
    input()

    page.goto(MAIL_WRITE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    print(f"iframe 개수: {page.locator('iframe').count()}")

    for i in range(page.locator("iframe").count()):
        iframe = page.locator("iframe").nth(i)
        print("-----")
        print(f"iframe index: {i}")
        print(f"id: {iframe.get_attribute('id')}")
        print(f"name: {iframe.get_attribute('name')}")
        print(f"src: {iframe.get_attribute('src')}")

    print("확인 완료")
    input("Enter를 누르면 종료합니다...")

    browser.close()

print("===== 메일 본문 에디터 확인 끝 =====")