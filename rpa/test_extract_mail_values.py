from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
import re
import math
import time

print("===== 메일 본문 값 추출 테스트 시작 =====")

report_date = datetime.now() - timedelta(days=1)
target_month = f"{report_date.year}-{report_date.month:02d}"
month_text = f"{report_date.month}월"

print(f"대상 월: {target_month}")

def to_k_text(value):
    number = int(str(value).replace(",", "").strip())
    return f"{round(number / 1000)}K"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    page.goto("http://localhost:5173")
    page.wait_for_timeout(3000)

    body_text = page.locator("body").inner_text()

    print("대시보드 텍스트 읽기 완료")

    target_value = None
    shipping_value = None

    # 월간플랜 카드: 예) 5월 목표 100K
    target_pattern = re.search(
        rf"{report_date.month}월\s*목표\s*([0-9,]+K)",
        body_text
    )

    if target_pattern:
        target_value = target_pattern.group(1)

    # 출하 누적: 예) 2026-05: Lot 21건 / 이동수량 34,608
    shipping_pattern = re.search(
        rf"{target_month}:\s*Lot\s*[0-9,]+건\s*/\s*이동수량\s*([0-9,]+)",
        body_text
    )

    if shipping_pattern:
        shipping_raw = shipping_pattern.group(1)
        shipping_value = to_k_text(shipping_raw)

    print(f"생산목표: {target_value}")
    print(f"출하 누적: {shipping_value}")

    if target_value is None:
        print("[ERROR] 생산목표를 찾지 못했습니다.")

    if shipping_value is None:
        print("[ERROR] 출하 누적 수량을 찾지 못했습니다.")

    time.sleep(10)
    browser.close()

print("===== 메일 본문 값 추출 테스트 끝 =====")