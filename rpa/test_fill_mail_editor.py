from playwright.sync_api import sync_playwright
import time

GROUPWARE_URL = "http://gw.ramostek.com/"
MAIL_WRITE_URL = "http://gw.ramostek.com/ekp/view/eml/emlMailRegPopup?mode=write"

print("===== 메일 본문 에디터 입력 테스트 시작 =====")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto(GROUPWARE_URL, wait_until="domcontentloaded", timeout=60000)

    print("그룹웨어 로그인 후 Enter를 누르세요.")
    input()

    page.goto(MAIL_WRITE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    editor_frame = page.frame_locator("#NamoSE_Ifr__gwNaoneditor1")

    test_body = """안녕하세요 3Camp 한훈혜 입니다.

본문 에디터 자동 입력 테스트입니다.

감사합니다."""

    print("본문 에디터에 테스트 문구 입력")

    editor_frame.locator("body").evaluate(
        """(body, value) => {
            body.innerHTML = value
                .split('\\n')
                .map(line => line ? `<p>${line}</p>` : '<p><br></p>')
                .join('');
        }""",
        test_body
    )

    print("화면에서 본문이 들어갔는지 확인하세요.")
    input("확인 후 Enter를 누르면 종료합니다...")

    browser.close()

print("===== 메일 본문 에디터 입력 테스트 끝 =====")