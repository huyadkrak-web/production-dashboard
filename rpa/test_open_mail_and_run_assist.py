from playwright.sync_api import sync_playwright
from pathlib import Path
import subprocess
import time

GROUPWARE_URL = "http://gw.ramostek.com/"
MAIL_WRITE_URL = "http://gw.ramostek.com/ekp/view/eml/emlMailRegPopup?mode=write"

PROJECT_DIR = Path(r"C:\Users\USER\Desktop\생산일보프로그램")

print("===== 그룹웨어 메일 작성 자동 연결 테스트 시작 =====")

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False
    )

    page = browser.new_page()

    print("그룹웨어 접속")

    page.goto(
        GROUPWARE_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    print("그룹웨어 로그인 후 Enter를 누르세요.")
    input()

    print("메일 작성창 직접 이동")

    page.goto(
        MAIL_WRITE_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    print("메일 작성창 로딩 대기")
    page.wait_for_timeout(5000)

    print("run_mail_assist.py 실행")

    process = subprocess.Popen(
        [
            "python",
            str(PROJECT_DIR / "rpa" / "run_mail_assist.py")
        ]
    )

    print("메일 작성 보조 실행 완료")
    print("run_mail_assist.py가 끝날 때까지 기다립니다.")

    process.wait()

    input("메일 작성/첨부 확인이 끝나면 Enter를 누르세요...")

    browser.close()

print("===== 그룹웨어 메일 작성 자동 연결 테스트 끝 =====")