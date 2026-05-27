from pathlib import Path

download_dir = Path(r"C:\Users\USER\Downloads")

pdf_files = list(download_dir.glob("생산일보_*.pdf"))

print("===== 최신 생산일보 PDF 찾기 시작 =====")

if not pdf_files:
    print("생산일보 PDF 파일을 찾지 못했습니다.")
else:
    latest_pdf = max(pdf_files, key=lambda file: file.stat().st_mtime)

    print(f"찾은 PDF 개수: {len(pdf_files)}")
    print(f"최신 PDF 파일명: {latest_pdf.name}")
    print(f"최신 PDF 경로: {latest_pdf}")

print("===== 최신 생산일보 PDF 찾기 끝 =====")