from pathlib import Path
from PIL import Image

# 원본 이미지
image_path = Path(
    r"C:\Users\USER\Desktop\생산일보프로그램\rpa\temp\report_page_2.png"
)

# 저장할 crop 이미지
output_path = Path(
    r"C:\Users\USER\Desktop\생산일보프로그램\rpa\temp\report_page_2_crop.png"
)

print("===== 2페이지 그래프 crop 시작 =====")

# 이미지 열기
image = Image.open(image_path)

# 원본 크기 확인
width, height = image.size

print(f"원본 이미지 크기: {width} x {height}")

# crop 비율 설정
# 필요하면 여기 숫자만 조정하면 됨
CROP_BOTTOM_RATIO = 0.38

# crop 영역 계산
left = 0
top = 0
right = width
bottom = int(height * CROP_BOTTOM_RATIO)

print(f"Crop 영역: ({left}, {top}) ~ ({right}, {bottom})")

# 이미지 crop
cropped_image = image.crop((left, top, right, bottom))

# 저장
cropped_image.save(output_path)

print(f"Crop 저장 완료: {output_path}")

print("===== 2페이지 그래프 crop 끝 =====")