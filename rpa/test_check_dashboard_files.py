from pathlib import Path

WORK_DIR = Path(r"C:\Users\USER\Desktop\작업일보")

REQUIRED_FILES = [
    "월간플랜.xlsx",
    "작업일보.xlsx",
    "코드별 불량현황.xlsx",
    "공장 받기.xlsx",
]

print("===== 대시보드 업로드 파일 확인 시작 =====")

missing_files = []

for file_name in REQUIRED_FILES:
    file_path = WORK_DIR / file_name

    if file_path.exists():
        print(f"[OK] 파일 확인: {file_name}")
    else:
        print(f"[ERROR] 파일 없음: {file_name}")
        missing_files.append(file_name)

print()

if missing_files:
    print("누락 파일이 있습니다.")
else:
    print("모든 업로드 파일 확인 완료")

print("===== 대시보드 업로드 파일 확인 끝 =====")