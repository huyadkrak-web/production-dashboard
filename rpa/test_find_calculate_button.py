from playwright.sync_api import sync_playwright
import time

print("===== 생산일보 계산 버튼 찾기 테스트 시작 =====")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto("http://localhost:5173")
    page.wait_for_timeout(3000)

    button = page.get_by_role("button", name="생산일보 계산")

    count = button.count()
    print(f"생산일보 계산 버튼 개수: {count}")

    if count > 0:
        print("[OK] 생산일보 계산 버튼을 찾았습니다.")
        print("아직 클릭하지 않았습니다.")
    else:
        print("[ERROR] 생산일보 계산 버튼을 찾지 못했습니다.")

    time.sleep(10)
    browser.close()

print("===== 생산일보 계산 버튼 찾기 테스트 끝 =====")