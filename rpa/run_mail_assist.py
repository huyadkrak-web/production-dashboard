from pathlib import Path
from io import BytesIO
from datetime import datetime, timedelta
import time
import json
import fitz
from PIL import Image
import pyautogui
import pyperclip
import win32clipboard


PROJECT_DIR = Path(r"C:\Users\USER\Desktop\생산일보프로그램")
DOWNLOAD_DIR = Path(r"C:\Users\USER\Downloads")
TEMP_DIR = PROJECT_DIR / "rpa" / "temp"
TEMP_DIR.mkdir(exist_ok=True)

TO_RECIPIENTS = (
    "tschang@ctst.co.kr; "
    "sjh@ctst.co.kr; "
    "ykjang@ctst.co.kr; "
    "msoh@ctst.co.kr; "
    "ktaejun@ctst.co.kr; "
    "ojs@ctst.co.kr; "
    "cge@ctst.co.kr"
)

CC_RECIPIENTS = "ws.sin@ctst.co.kr"

REPORT_DATE = datetime.now() - timedelta(days=1)

PRODUCT_NAME = "V6P 132FBGA-2Chip Stack"

MAIL_VALUES_PATH = TEMP_DIR / "mail_values.json"


def load_mail_values():
    if not MAIL_VALUES_PATH.exists():
        print("메일 값 파일이 없어 기본값을 사용합니다.")
        return {
            "monthly_target": "확인필요",
            "shipping_qty": "확인필요",
        }

    with open(MAIL_VALUES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def countdown(message, seconds=5):
    print(message)
    for i in range(seconds, 0, -1):
        print(f"{i}초...")
        time.sleep(1)


def find_latest_pdf():
    pdf_files = list(DOWNLOAD_DIR.glob("생산일보_*.pdf"))
    if not pdf_files:
        raise FileNotFoundError("생산일보 PDF 파일을 찾지 못했습니다.")
    latest_pdf = max(pdf_files, key=lambda file: file.stat().st_mtime)
    print(f"최신 PDF: {latest_pdf}")
    return latest_pdf


def pdf_to_images(pdf_path):
    print("PDF 이미지를 변환합니다.")
    doc = fitz.open(pdf_path)

    for page_index in range(len(doc)):
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        image_path = TEMP_DIR / f"report_page_{page_index + 1}.png"
        pix.save(image_path)
        print(f"저장 완료: {image_path}")

    doc.close()


def crop_page2_graph():
    source = TEMP_DIR / "report_page_2.png"
    output = TEMP_DIR / "report_page_2_crop.png"

    if not source.exists():
        print("2페이지 이미지가 없어 crop을 건너뜁니다.")
        return None

    image = Image.open(source)
    width, height = image.size

    crop_bottom_ratio = 0.38
    cropped = image.crop((0, 0, width, int(height * crop_bottom_ratio)))
    cropped.save(output)

    print(f"2페이지 그래프 crop 완료: {output}")
    return output


def make_mail_subject():
    return (
        f"CTST 3Camp 생산일보 "
        f"({REPORT_DATE.year % 100:02d}-{REPORT_DATE.month:02d}-{REPORT_DATE.day:02d})"
    )


def make_mail_body():
    mail_values = load_mail_values()

    monthly_target = mail_values.get("monthly_target", "확인필요")
    shipping_qty = mail_values.get("shipping_qty", "확인필요")

    date_text = f"{REPORT_DATE.year % 100}년 {REPORT_DATE.month}월 {REPORT_DATE.day}일"
    month = REPORT_DATE.month

    return f"""안녕하세요 3Camp 한훈혜 입니다.

{date_text} 생산일보 전달 드립니다.

- {month}월 {PRODUCT_NAME}의 생산목표는 {monthly_target} 입니다.

- {month}월 출하 누적 수량 {shipping_qty} 입니다.

감사합니다."""


def paste_text(text):
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")


def copy_image_to_clipboard(image_path):
    image = Image.open(image_path)

    output = BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()

    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()


def paste_images(image_paths):
    for image_path in image_paths:
        if not image_path or not Path(image_path).exists():
            continue

        print(f"이미지 붙여넣기: {image_path}")
        copy_image_to_clipboard(image_path)
        pyautogui.hotkey("ctrl", "v")
        pyautogui.press("enter")
        pyautogui.press("enter")
        time.sleep(2)


def attach_pdf(pdf_path):
    print("파일 선택창에 PDF 경로를 입력합니다.")
    print(f"첨부할 PDF: {pdf_path}")

    pyperclip.copy(str(pdf_path))

    time.sleep(1)

    # 파일 선택창의 '파일 이름' 입력칸으로 이동 시도
    pyautogui.hotkey("alt", "n")
    time.sleep(0.5)

    # 경로 붙여넣기
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1)

    # 열기
    pyautogui.press("enter")


def main():
    print("===== 생산일보 메일 작성 보조 시작 =====")

    latest_pdf = find_latest_pdf()
    pdf_to_images(latest_pdf)
    page2_crop = crop_page2_graph()
    mail_body = make_mail_body()
    mail_subject = make_mail_subject()

    print("\n0단계-1: 받는 사람 입력칸을 클릭하세요.")
    input("받는 사람 칸 클릭 완료 후 Enter를 누르세요...")

    countdown("받는 사람 입력 전입니다. 받는 사람 칸이 선택되어 있는지 확인하세요.", 5)

    paste_text(TO_RECIPIENTS)

    pyautogui.press("enter")

    print("\n0단계-2: 참조 입력칸을 클릭하세요.")
    input("참조 칸 클릭 완료 후 Enter를 누르세요...")

    countdown("참조 입력 전입니다. 참조 칸이 선택되어 있는지 확인하세요.", 5)

    paste_text(CC_RECIPIENTS)

    pyautogui.press("enter")

    print("\n0단계-3: 제목 입력칸을 클릭하세요.")
    input("제목 칸 클릭 완료 후 Enter를 누르세요...")

    countdown("제목 입력 전입니다. 제목 칸이 선택되어 있는지 확인하세요.", 5)

    paste_text(mail_subject)

    print("\n1단계: 그룹웨어 메일 작성창 본문 빈칸을 클릭하세요.")
    input("본문 빈칸 클릭 완료 후 Enter를 누르세요...")

    countdown("본문 붙여넣기 전입니다. 메일 본문칸이 선택되어 있는지 확인하세요.", 5)
    paste_text(mail_body)

    pyautogui.press("enter")
    pyautogui.press("enter")
    time.sleep(1)

    image_list = [
        TEMP_DIR / "report_page_1.png",
        page2_crop,
    ]

    countdown("이미지 붙여넣기 전입니다. 아직 메일 본문칸이 선택되어 있는지 확인하세요.", 5)
    paste_images(image_list)

    print("\n2단계: 그룹웨어에서 첨부 > 내 PC를 눌러 파일 선택창을 여세요.")
    input("파일 선택창이 열린 상태에서 Enter를 누르세요...")

    countdown("PDF 경로 입력 전입니다. 파일 선택창이 선택되어 있는지 확인하세요.", 5)
    attach_pdf(latest_pdf)

    print("===== 완료: 발송 전 반드시 직접 확인하세요 =====")


if __name__ == "__main__":
    main()