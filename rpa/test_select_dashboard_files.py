from pathlib import Path
from playwright.sync_api import sync_playwright
import time

WORK_DIR = Path(r"C:\Users\USER\Desktop\작업일보")

monthly_plan = WORK_DIR / "월간플랜.xlsx"
work_report = WORK_DIR / "작업일보.xlsx"
defect_report = WORK_DIR / "코드별 불량현황.xlsx"
shipment_file = WORK_DIR / "공장 받기.xlsx"

files = [monthly_plan, work_report, defect_report, shipment_file]

print("===== 대시보드 파일 자동 선택 테스트 시작 =====")

for file in files:
    if not file.exists():
        print(f"[ERROR] 파일 없음: {file}")
        raise SystemExit

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto("http://localhost:5173")
    page.wait_for_timeout(3000)

    file_inputs = page.locator("input[type='file']")
    count = file_inputs.count()

    print(f"파일 선택 input 개수: {count}")

    if count < 4:
        print("[ERROR] 파일 선택 input이 4개보다 적습니다.")
        print("대시보드 화면이 완전히 열렸는지 확인하세요.")
        time.sleep(10)
        browser.close()
        raise SystemExit

    print("월간플랜 선택 중...")
    file_inputs.nth(0).set_input_files(str(monthly_plan))

    print("작업일보 선택 중...")
    file_inputs.nth(1).set_input_files(str(work_report))

    print("코드별 불량현황 선택 중...")
    file_inputs.nth(2).set_input_files(str(defect_report))

    print("공장 받기 선택 중...")
    file_inputs.nth(3).set_input_files(str(shipment_file))

    print("파일 자동 선택 완료")
    print("화면에서 파일명이 제대로 들어갔는지 확인하세요.")
    print("아직 계산 버튼은 누르지 않았습니다.")

    time.sleep(20)

    browser.close()

print("===== 대시보드 파일 자동 선택 테스트 끝 =====")