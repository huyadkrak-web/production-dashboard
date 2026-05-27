from playwright.sync_api import sync_playwright
import re
import math
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    page.goto("http://localhost:5173")

    # 페이지 로딩 대기
    page.wait_for_timeout(5000)

    # 전체 텍스트 읽기
    full_text = page.locator("body").inner_text()

    print("===== 출하 누적 분석 시작 =====")

    # 2026-05 이동수량 찾기
    match = re.search(r"2026-05: Lot \d+건 / 이동수량 ([\d,]+)", full_text)

    if match:
        qty_text = match.group(1)

        # 쉼표 제거
        qty_number = int(qty_text.replace(",", ""))

        # K 단위 반올림
        qty_k = math.ceil(qty_number / 1000)

        print(f"원본 이동수량: {qty_text}")
        print(f"숫자 변환: {qty_number}")
        print(f"메일 표시용: {qty_k}K")

    else:
        print("2026-05 이동수량을 찾지 못했습니다.")

    print("===== 출하 누적 분석 끝 =====")

    time.sleep(10)

    browser.close()
    