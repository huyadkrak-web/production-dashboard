from pathlib import Path
from PIL import Image

image_path = Path(
    r"C:\Users\USER\Desktop\생산일보프로그램\rpa\temp\report_page_1.png"
)

print("이미지 열기 시작")

img = Image.open(image_path)

img.show()

print("이미지 열기 완료")