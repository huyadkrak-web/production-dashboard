from pathlib import Path
from PIL import Image
import win32clipboard
from io import BytesIO

image_path = Path(
    r"C:\Users\USER\Desktop\생산일보프로그램\rpa\temp\report_page_1.png"
)

print("===== 이미지 클립보드 복사 시작 =====")

image = Image.open(image_path)

# BMP 형식으로 변환
output = BytesIO()
image.convert("RGB").save(output, "BMP")

data = output.getvalue()[14:]
output.close()

# 클립보드 복사
win32clipboard.OpenClipboard()
win32clipboard.EmptyClipboard()
win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
win32clipboard.CloseClipboard()

print("클립보드 이미지 복사 완료!")
print("이제 Ctrl + V 붙여넣기 가능합니다.")
