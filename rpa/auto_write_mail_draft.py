from pathlib import Path
from io import BytesIO
from datetime import datetime, timedelta
import json
import time
import fitz
from PIL import Image
from playwright.sync_api import sync_playwright
import pyautogui
import pyperclip
import win32clipboard
from cryptography.fernet import Fernet
import configparser

GROUPWARE_URL = "http://gw.ramostek.com/"
MAIL_WRITE_URL = "http://gw.ramostek.com/ekp/view/eml/emlMailRegPopup?mode=write"

PROJECT_DIR = Path(r"C:\Users\USER\Desktop\생산일보프로그램")
DOWNLOAD_DIR = Path(r"C:\Users\USER\Downloads")
TEMP_DIR = PROJECT_DIR / "rpa" / "temp"
TEMP_DIR.mkdir(exist_ok=True)

MAIL_VALUES_PATH = TEMP_DIR / "mail_values.json"
CONFIG_PATH = PROJECT_DIR / "Login.cfg"
KEY_PATH = PROJECT_DIR / "login_crypto.key"

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


def load_mail_values():
    if not MAIL_VALUES_PATH.exists():
        return {"monthly_target": "확인필요", "shipping_qty": "확인필요"}

    with open(MAIL_VALUES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def find_latest_pdf():
    pdf_files = list(DOWNLOAD_DIR.glob("생산일보_*.pdf"))
    if not pdf_files:
        raise FileNotFoundError("생산일보 PDF 파일을 찾지 못했습니다.")
    return max(pdf_files, key=lambda file: file.stat().st_mtime)

def pdf_to_report_images(pdf_path):
    print("메일용 PDF 이미지를 다시 생성합니다.")

    doc = fitz.open(pdf_path)

    for page_index in range(len(doc)):
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        image_path = TEMP_DIR / f"report_page_{page_index + 1}.png"
        pix.save(image_path)
        print(f"저장 완료: {image_path}")

    doc.close()


def crop_report_page2_graph():
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

page1_image = TEMP_DIR / "report_page_1.png"
page2_crop = TEMP_DIR / "report_page_2_crop.png"


def make_mail_subject():
    return (
        f"CTST 3Camp 생산일보 "
        f"({REPORT_DATE.year % 100:02d}-{REPORT_DATE.month:02d}-{REPORT_DATE.day:02d})"
    )


def make_mail_body_text():
    values = load_mail_values()

    monthly_target = values.get("monthly_target", "확인필요")
    shipping_qty = values.get("shipping_qty", "확인필요")

    month = REPORT_DATE.month
    date_text = f"{REPORT_DATE.year % 100}년 {month}월 {REPORT_DATE.day}일"

    return f"""안녕하세요 3Camp 한훈혜 입니다.

{date_text} 생산일보 전달 드립니다.

- {month}월 {PRODUCT_NAME}의 생산목표는 {monthly_target} 입니다.

- {month}월 출하 누적 수량 {shipping_qty} 입니다.

감사합니다."""


def paste_text(text):
    pyperclip.copy(text)
    time.sleep(0.5)
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


def paste_image(image_path):
    if not image_path or not Path(image_path).exists():
        return

    print(f"이미지 붙여넣기: {image_path}")
    copy_image_to_clipboard(image_path)
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(2)
    pyautogui.press("enter")
    pyautogui.press("enter")


def set_input_value(page, selector, value):
    page.locator(selector).evaluate(
        """(el, value) => {
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }""",
        value,
    )

def load_login_config():

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Login.cfg 없음: {CONFIG_PATH}"
        )

    if not KEY_PATH.exists():
        raise FileNotFoundError(
            f"login_crypto.key 없음: {KEY_PATH}"
        )

    config = configparser.ConfigParser()
    config.read(CONFIG_PATH, encoding="utf-8")

    user_id = config["GROUPWARE"]["ID"]
    encrypted_pw = config["GROUPWARE"]["PASSWORD"]

    with open(KEY_PATH, "rb") as f:
        key = f.read()

    cipher = Fernet(key)

    user_pw = cipher.decrypt(
        encrypted_pw.encode("utf-8")
    ).decode("utf-8")

    return user_id, user_pw


def try_auto_login(page):

    print("자동 로그인 확인")

    print("현재 URL:", page.url)
    print("페이지 제목:", page.title())
    print("iframe 개수:", page.locator("iframe").count())
    print("input 개수:", page.locator("input").count())

    user_id, user_pw = load_login_config()

    page.wait_for_timeout(3000)

    login_inputs = page.locator("input")
    input_count = login_inputs.count()

    print(f"3초 대기 후 로그인 input 개수: {input_count}")

    if input_count < 2:
        print("로그인 input을 찾지 못했습니다.")
        print("iframe 안에 로그인칸이 있을 수 있습니다.")
        return

    try:
        page.bring_to_front()
        page.wait_for_timeout(1000)

        print("아이디 입력")

        page.locator("#userId").click()
        paste_text(user_id)

        print("비밀번호 입력")

        pyautogui.press("tab")
        time.sleep(0.5)
        paste_text(user_pw)

        print("로그인 실행")

        pyautogui.press("enter")

        page.wait_for_timeout(5000)

        print("자동 로그인 완료 시도")
        print("로그인 후 URL:", page.url)

        if "login" in page.url:
            raise RuntimeError(
                "자동 로그인 후에도 로그인 페이지입니다. 아이디/비밀번호 또는 로그인 실행 방식을 확인해야 합니다."
            )

    except Exception as e:
        print(f"[WARN] 자동 로그인 실패: {e}")
        raise


print("===== 그룹웨어 메일 자동 작성 시작 =====")

latest_pdf = find_latest_pdf()
print(f"첨부 PDF: {latest_pdf}")

print("PDF 렌더 안정화 대기")
time.sleep(8)

pdf_to_report_images(latest_pdf)
page2_crop = crop_report_page2_graph()

with sync_playwright() as p:
    browser = p.chromium.launch(
    headless=False,
    channel="chrome"
)
    page = browser.new_page()

    print("그룹웨어 접속")
    page.goto(GROUPWARE_URL, wait_until="domcontentloaded", timeout=60000)

    try_auto_login(page)

    print("메일 작성창 이동")
    page.goto(MAIL_WRITE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    print("받는사람 입력")
    to_input = page.locator("#s2id_emlMailReg_mailToText input[type='text']")
    to_input.click()
    to_input.fill(TO_RECIPIENTS)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)

    print("참조 입력")
    cc_input = page.locator("#s2id_emlMailReg_mailCcText input[type='text']")
    cc_input.click()
    cc_input.fill(CC_RECIPIENTS)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)

    print("제목 입력")
    set_input_value(page, "#emlMailReg_subject", make_mail_subject())

    print("PDF 첨부")
    page.locator("input[type='file']").set_input_files(str(latest_pdf))
    page.wait_for_timeout(2000)

    print("본문 에디터 클릭")
    page.bring_to_front()
    page.wait_for_timeout(1000)
    editor_frame = page.frame_locator("#NamoSE_Ifr__gwNaoneditor1")
    editor_frame.locator("body").click()
    page.wait_for_timeout(1000)

    print("본문 실제 붙여넣기")
    paste_text(make_mail_body_text())

    pyautogui.press("enter")
    pyautogui.press("enter")
    time.sleep(1)

    print("이미지 실제 붙여넣기")
    paste_image(page1_image)
    paste_image(page2_crop)

    print("===== 메일 자동 작성 완료 =====")
    print("미리보기 확인 후 발송 버튼만 직접 눌러주세요.")

    input("확인 후 Enter를 누르면 종료합니다...")

    browser.close()

print("===== 그룹웨어 메일 자동 작성 끝 =====")