from playwright.sync_api import sync_playwright
import time

GROUPWARE_URL = "http://gw.ramostek.com/"
MAIL_WRITE_URL = "http://gw.ramostek.com/ekp/view/eml/emlMailRegPopup?mode=write"

print("===== 그룹웨어 메일 작성창 직접 이동 테스트 시작 =====")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    print("그룹웨어 접속 중...")
    page.goto(GROUPWARE_URL, wait_until="domcontentloaded", timeout=60000)

    print("로그인하세요.")
    input("로그인 완료 후 Enter를 누르세요...")

    print("메일 작성창 주소로 직접 이동합니다.")
    page.goto(MAIL_WRITE_URL, wait_until="domcontentloaded", timeout=60000)

    print("메일 작성창이 열렸는지 확인하세요.")
    time.sleep(30)

    browser.close()

print("===== 그룹웨어 메일 작성창 직접 이동 테스트 끝 =====")