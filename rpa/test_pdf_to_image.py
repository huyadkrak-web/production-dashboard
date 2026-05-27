from pathlib import Path
import fitz  # PyMuPDF

download_dir = Path(r"C:\Users\USER\Downloads")
output_dir = Path(r"C:\Users\USER\Desktop\생산일보프로그램\rpa\temp")
output_dir.mkdir(exist_ok=True)

pdf_files = list(download_dir.glob("생산일보_*.pdf"))

print("===== PDF 이미지 변환 시작 =====")

if not pdf_files:
    print("생산일보 PDF 파일을 찾지 못했습니다.")
    raise SystemExit

latest_pdf = max(pdf_files, key=lambda file: file.stat().st_mtime)
print(f"최신 PDF: {latest_pdf}")

doc = fitz.open(latest_pdf)

for page_index in range(len(doc)):
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    image_path = output_dir / f"report_page_{page_index + 1}.png"
    pix.save(image_path)
    print(f"저장 완료: {image_path}")

doc.close()

print("===== PDF 이미지 변환 끝 =====")