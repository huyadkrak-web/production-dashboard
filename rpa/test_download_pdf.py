from datetime import datetime, timedelta
from pathlib import Path
import re
import json
from playwright.sync_api import sync_playwright
import time

WORK_DIR = Path(r"\\59.12.17.16\shareks\work_report")

LOCAL_DIR = Path(
    r"C:\Users\USER\Desktop\작업일보"
)

DOWNLOAD_DIR = Path(
    r"C:\Users\USER\Downloads"
)

# 월간플랜은 기존 로컬 사용
monthly_plan = LOCAL_DIR / "월간플랜.xlsx"

# =========================
# 작업일보 파일 선택
# =========================

work_report_candidates = list(
    WORK_DIR.glob("작업일보_*.xlsx")
)

if not work_report_candidates:
    raise FileNotFoundError(
        "작업일보 파일을 찾지 못했습니다."
    )

work_report = max(
    work_report_candidates,
    key=lambda file: file.stat().st_mtime
)

print(f"선택된 작업일보: {work_report.name}")

# =========================
# 코드별 불량현황 파일 선택
# =========================

defect_report_candidates = list(
    WORK_DIR.glob("코드별불량현황_*.xlsx")
)

if not defect_report_candidates:
    raise FileNotFoundError(
        "코드별불량현황 파일을 찾지 못했습니다."
    )

defect_report = max(
    defect_report_candidates,
    key=lambda file: file.stat().st_mtime
)

print(f"선택된 불량현황: {defect_report.name}")

# =========================
# 출하파일 자동 수집
# =========================

shipment_candidates = list(
    WORK_DIR.glob("공장받기*.xlsx")
)

if not shipment_candidates:
    print("출하파일 없음")
    shipment_files = []

else:
    latest_shipment_time = max(
        file.stat().st_mtime
        for file in shipment_candidates
    )

    shipment_files = [
        file
        for file in shipment_candidates
        if abs(
            file.stat().st_mtime
            - latest_shipment_time
        ) < 300
    ]

    shipment_files = sorted(shipment_files)

    print("선택된 출하파일:")
    for file in shipment_files:
        print(f"- {file.name}")

print("===== 생산일보 PDF 다운로드 자동화 시작 =====")

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

    context = browser.new_context(
        accept_downloads=True
    )

    page = context.new_page()

    page.goto("http://localhost:5173")
    page.wait_for_timeout(3000)

    print(f"기준일 입력: {date_text}")

    page.get_by_test_id(
        "report-date-input"
    ).fill(date_text)

    print("기준정보 불러오기")

    page.get_by_test_id(
        "load-master-button"
    ).evaluate("button => button.click()")

    page.wait_for_timeout(2000)

    print("월간플랜 파일 선택")
    page.get_by_test_id(
        "monthly-plan-file"
    ).set_input_files(str(monthly_plan))

    print("작업일보 파일 선택")
    page.get_by_test_id(
        "work-report-file"
    ).set_input_files(str(work_report))

    print("코드별 불량현황 파일 선택")
    page.get_by_test_id(
        "defect-report-file"
    ).set_input_files(str(defect_report))

    page.wait_for_timeout(1000)

    print("생산일보 계산 버튼 클릭")

    page.get_by_test_id(
    "run-production-report-button"
    ).evaluate("button => button.click()")

    print("생산일보 계산 대기")
    page.wait_for_timeout(5000)

    if existing_shipment_files:

        for shipment_file in existing_shipment_files:

            print(f"출하파일 선택: {shipment_file.name}")

            page.get_by_test_id(
                 "shipment-file"
            ).set_input_files(str(shipment_file))

            page.wait_for_timeout(1000)

            print("출하 파일 업로드 클릭")

            page.once(
                "dialog",
                lambda dialog: dialog.accept()
            )

            page.get_by_test_id(
                "upload-shipment-button"
            ).evaluate("button => button.click()")

            print("출하파일 업로드 완료 대기")
            page.wait_for_timeout(5000)

    print("공정불량 자동 계산 클릭")

    page.once(
        "dialog",
        lambda dialog: dialog.accept()
    )

    page.get_by_test_id(
        "run-defect-auto-button"
    ).evaluate("button => button.click()")

    print("공정불량 자동 계산 완료 대기")
    page.wait_for_timeout(25000)

    print("PDF 다운로드 전 화면 안정화 대기")
    page.wait_for_timeout(5000)

    pdf_button = page.get_by_test_id(
    "download-pdf-button"
    )

    if pdf_button.is_disabled():
        print("[ERROR] PDF 다운로드 버튼이 비활성화 상태입니다.")
        time.sleep(10)
        browser.close()
        raise SystemExit
    print("메일 본문용 값 추출 시작")

    body_text = page.locator("body").inner_text()

    # =========================
    # 월간플랜 목표값 추출
    # =========================

    target_pattern = re.search(
        rf"{report_date.month}월\s*목표\s*([0-9,]+K)",
        body_text
    )

    monthly_target = (
        target_pattern.group(1)
        if target_pattern
        else "확인필요"
    )

    # =========================
    # 출하 누적 추출
    # =========================

    shipping_pattern = re.search(
        rf"출하\s*누적[\s\S]*?{date_text[:7]}:\s*Lot\s*[0-9,]+건\s*/\s*이동수량\s*([0-9,]+)",
        body_text
    )

    if shipping_pattern:
        shipping_raw = shipping_pattern.group(1).replace(",", "")
        shipping_qty = f"{round(int(shipping_raw) / 1000)}K"
    else:
        shipping_qty = "확인필요"

    # =========================
    # 저장
    # =========================

    mail_values = {
        "monthly_target": monthly_target,
        "shipping_qty": shipping_qty,
        "target_month": report_date.month,
        "report_date": date_text,
    }

    temp_dir = Path(
        r"C:\Users\USER\Desktop\생산일보프로그램\rpa\temp"
    )

    temp_dir.mkdir(exist_ok=True)

    mail_values_path = temp_dir / "mail_values.json"

    with open(mail_values_path, "w", encoding="utf-8") as f:
        json.dump(
            mail_values,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("메일 본문용 값 저장 완료")
    print(f"생산목표: {monthly_target}")
    print(f"출하 누적: {shipping_qty}")
    print(f"저장 위치: {mail_values_path}")

    print("PDF 다운로드 시작")

    with page.expect_download() as download_info:
        pdf_button.evaluate("button => button.click()")

    download = download_info.value

    suggested_name = download.suggested_filename
    save_path = DOWNLOAD_DIR / suggested_name

    download.save_as(str(save_path))

    print("PDF 다운로드 완료")
    print(f"파일명: {suggested_name}")
    print(f"저장 위치: {save_path}")

    time.sleep(10)

    browser.close()

print("===== 생산일보 PDF 다운로드 자동화 끝 =====")