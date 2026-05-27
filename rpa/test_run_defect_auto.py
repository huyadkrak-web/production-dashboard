from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright
import time

WORK_DIR = Path(r"C:\Users\USER\Desktop\작업일보")

monthly_plan = WORK_DIR / "월간플랜.xlsx"
work_report = WORK_DIR / "작업일보.xlsx"
defect_report = WORK_DIR / "코드별 불량현황.xlsx"

shipment_files = [
    WORK_DIR / "공장 받기.xlsx",
    WORK_DIR / "공장 받기_2.xlsx",
]

print("===== 공정불량 자동 계산 테스트 시작 =====")

required_files = [monthly_plan, work_report, defect_report]

for file_path in required_files:
    if not file_path.exists():
        print(f"[ERROR] 필수 파일 없음: {file_path}")
        raise SystemExit

existing_shipment_files = [
    file_path for file_path in shipment_files if file_path.exists()
]

if existing_shipment_files:
    print("출하파일 확인:")
    for file_path in existing_shipment_files:
        print(f"- {file_path.name}")
else:
    print("출하파일 없음: 출하 업로드 없이 진행")

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
    page.get_by_role(
        "button",
        name="불러오기"
    ).nth(0).evaluate("button => button.click()")

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
    page.get_by_role(
        "button",
        name="생산일보 계산"
    ).evaluate("button => button.click()")

    print("생산일보 계산 대기")
    page.wait_for_timeout(5000)

    if existing_shipment_files:
        print("출하파일 선택")
        file_inputs.nth(3).set_input_files(
            [str(file_path) for file_path in existing_shipment_files]
        )

        page.wait_for_timeout(1000)

        print("출하 파일 업로드 클릭")

        page.once("dialog", lambda dialog: dialog.accept())

        page.get_by_role(
            "button",
            name="출하 파일 업로드"
        ).evaluate("button => button.click()")

        print("출하파일 업로드 완료 대기")
        page.wait_for_timeout(3000)

    print("공정불량 자동 계산 클릭")

    page.once("dialog", lambda dialog: dialog.accept())

    page.get_by_role(
        "button",
        name="공정불량 자동 계산"
    ).evaluate("button => button.click()")

    print("공정불량 자동 계산 완료 대기")
    page.wait_for_timeout(10000)

    print("화면 확인 대기")
    time.sleep(15)

    browser.close()

print("===== 공정불량 자동 계산 테스트 끝 =====")