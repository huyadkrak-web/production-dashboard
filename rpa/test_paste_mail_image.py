from pathlib import Path
from PIL import Image
import win32clipboard
from io import BytesIO
import pyautogui
import time

image_paths = [
    r"C:\Users\USER\Desktop\생산일보프로그램\rpa\temp\report_page_1.png",
    r"C:\Users\USER\Desktop\생산일보프로그램\rpa\temp\report_page_2_crop.png"
]

print("===== 메일 이미지 붙여넣기 테스트 =====")

print("5초 안에 메일 본문 입력칸 클릭하세요.")

time.sleep(5)

for image_path in image_paths:

    print(f"붙여넣는 중: {image_path}")

    image = Image.open(image_path)

    output = BytesIO()
    image.convert("RGB").save(output, "BMP")

    data = output.getvalue()[14:]
    output.close()

    # 클립보드 복사
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()

    # 붙여넣기
    pyautogui.hotkey("ctrl", "v")

    # 이미지 사이 줄바꿈
    pyautogui.press("enter")
    pyautogui.press("enter")

    time.sleep(2)

print("메일 이미지 전체 붙여넣기 완료!")