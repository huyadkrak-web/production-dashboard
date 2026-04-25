# -*- coding: utf-8 -*-
"""Analyze Excel sheet structure. Run: python analyze_excel.py [path_to.xlsx]
   Or put path in excel_path.txt (UTF-8), or place 3Camp_260311.xlsx in project root."""
import sys
from pathlib import Path

def main():
    if len(sys.argv) >= 2:
        path = Path(sys.argv[1])
    else:
        candidates = [
            Path(__file__).resolve().parent.parent / "3Camp_260311.xlsx",
        ]
        path_file = Path(__file__).resolve().parent / "excel_path.txt"
        if path_file.exists():
            candidates.insert(0, Path(path_file.read_text(encoding="utf-8").strip()))
        path = None
        for p in candidates:
            if p.exists():
                path = p
                break
        if path is None:
            path = candidates[0]
    if not path.exists():
        out_lines = [f"File not found: {path}", "Usage: python analyze_excel.py <path_to_3Camp_260311.xlsx>"]
        out_path = Path(__file__).resolve().parent / "analyze_result.txt"
        out_path.write_text("\n".join(out_lines), encoding="utf-8")
        print(out_lines[0])
        sys.exit(1)

    import pandas as pd
    xls = pd.ExcelFile(path, engine="openpyxl")
    lines = ["=== Sheet names ===", str(xls.sheet_names), ""]
    target_sheets = ["기준", "물량 투입 Plan", "작업일보", "전일작업일보"]
    for name in target_sheets:
        if name not in xls.sheet_names:
            lines.append(f"--- Sheet '{name}' NOT FOUND ---")
            lines.append("")
            continue
        df = pd.read_excel(xls, sheet_name=name, nrows=0)
        cols = list(df.columns)
        lines.append(f"--- Sheet: {name!r} (columns: {len(cols)}) ---")
        for i, c in enumerate(cols):
            lines.append(f"  [{i}] {c!r}")
        lines.append("")
    xls.close()
    result_text = "\n".join(lines)
    out_path = Path(__file__).resolve().parent / "analyze_result.txt"
    out_path.write_text(result_text, encoding="utf-8")
    print(result_text)

if __name__ == "__main__":
    main()
