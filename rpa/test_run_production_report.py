from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright
import time

WORK_DIR = Path(r"C:\Users\USER\Desktop\작업일보")

monthly_plan = WORK_DIR / "월간플랜.xlsx"
work_report = WORK_DIR / "작업일보.xlsx"
defect_report = WORK_DIR / "코드별 불량현황.xlsx"

print("===== 생산일보 계산 테스트 시작 =====")

for file_path in [monthly_plan, work_report, defect_report]:
    if not file_path.exists():
        print(f"[ERROR] 파일 없음: {file_path}")
        raise SystemExit

report_date = datetime.now() - timedelta(days=1)
date_text = report_date.strftime("%Y-%m-%d")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    page.goto("http://localhost:5173")
    page.wait_for_timeout(3000)

    print(f"기준일 입력: {date_text}")
    page.locator("input[type='date']").first.fill(date_text)

    print("기준정보 불러오기")
    load_button = page.get_by_role("button", name="불러오기").nth(0)
    load_button.evaluate("button => button.click()")

    page.wait_for_timeout(2000)

    file_inputs = page.locator("input[type='file']")

    print("월간플랜 파일 선택")
    file_inputs.nth(0).set_input_files(str(monthly_plan))

    print("작업일보 파일 선택")
    file_inputs.nth(1).set_input_files(str(work_report))

    print("코드별 불량현황 파일 선택")
    file_inputs.nth(2).set_input_files(str(defect_report))

    page.wait_for_timeout(1000)

    print("생산일보 계산 버튼 클릭")

    calc_button = page.get_by_role(
        "button",
        name="생산일보 계산"
    )

    calc_button.evaluate("button => button.click()")

    print("생산일보 계산 진행 확인 대기")
    time.sleep(15)

    browser.close()

print("===== 생산일보 계산 테스트 끝 =====")