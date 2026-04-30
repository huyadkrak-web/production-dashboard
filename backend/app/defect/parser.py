"""엑셀 출하·불량 파일을 DataFrame으로 파싱합니다."""

from __future__ import annotations

import io

import pandas as pd

# 출하(공장 받기) 엑셀: 다중 시트 시 이 이름이 있으면 우선 사용
_SHIPMENT_SHEET_PREFERRED = "공장 받기@2"


def _select_shipment_sheet_name(sheet_names: list[str]) -> str:
    """시트 선택: '공장 받기@2' → 두 번째 시트 → 첫 시트."""
    if not sheet_names:
        raise ValueError("엑셀에 시트가 없습니다.")
    if _SHIPMENT_SHEET_PREFERRED in sheet_names:
        return _SHIPMENT_SHEET_PREFERRED
    if len(sheet_names) >= 2:
        return sheet_names[1]
    return sheet_names[0]


def _clean_lot(x):
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _norm(x):
    return str(x).strip().replace(" ", "").upper()


def parse_shipment(file_bytes: bytes) -> pd.DataFrame:
    """공장 받기.xlsx(출하) 형식: D4 이동일자, 7행부터 C/E/I 열 데이터."""
    bio = io.BytesIO(file_bytes)
    xl = pd.ExcelFile(bio, engine="openpyxl")
    selected_sheet_name = _select_shipment_sheet_name(list(xl.sheet_names))
    print("shipment sheet:", selected_sheet_name)

    head = pd.read_excel(
        xl,
        sheet_name=selected_sheet_name,
        header=None,
        nrows=4,
    )
    move_date = pd.to_datetime(head.iloc[3, 3], errors="coerce")

    df = pd.read_excel(
        xl,
        sheet_name=selected_sheet_name,
        header=None,
        skiprows=6,
        usecols=[2, 4, 8],
    )
    df.columns = ["lot_id", "product", "move_qty"]

    df["lot_id"] = df["lot_id"].map(_clean_lot)
    df = df[df["lot_id"].ne("")].copy()

    df["move_qty"] = pd.to_numeric(df["move_qty"], errors="coerce").fillna(0)
    df["move_date"] = move_date

    out = df[["lot_id", "product", "move_qty", "move_date"]]
    print(f"[parse_shipment] shape={out.shape}")
    return out


def parse_defect(file_bytes: bytes) -> pd.DataFrame:
    """코드별 불량현황.xlsx: '부모 LOTID' 헤더 행 자동 탐지 후 K열 등 매핑."""
    raw = pd.read_excel(io.BytesIO(file_bytes), header=None, engine="openpyxl")

    header_row_idx: int | None = None
    for i in range(len(raw)):
        for val in raw.iloc[i]:
            if pd.notna(val) and _norm(val) == "부모LOTID":
                header_row_idx = i
                break
        if header_row_idx is not None:
            break

    if header_row_idx is None:
        raise ValueError("헤더 행에서 '부모 LOTID' 셀을 찾지 못했습니다.")

    df = raw.iloc[header_row_idx + 1 :].copy()
    df.columns = [
        str(x).strip() if pd.notna(x) else "" for x in raw.iloc[header_row_idx]
    ]

    rename: dict[str, str] = {}
    for c in df.columns:
        key = str(c).strip()
        if key == "부모 LOTID":
            rename[c] = "lot_id"
        elif key == "불량수량":
            rename[c] = "defect_qty"
        elif key == "불량명":
            rename[c] = "defect_name"

    df = df.rename(columns=rename)
    required = ("lot_id", "defect_qty", "defect_name")
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {missing}")

    df = df[list(required)].copy()
    df["lot_id"] = df["lot_id"].map(_clean_lot)
    df = df[df["lot_id"].ne("")].copy()

    df["defect_qty"] = pd.to_numeric(df["defect_qty"], errors="coerce").fillna(0)

    out = df[["lot_id", "defect_qty", "defect_name"]]
    print(f"[parse_defect] shape={out.shape}")
    return out


def parse_work(file_bytes: bytes) -> pd.DataFrame:
    """작업일보에서 LOT·공정ID·투입수량을 파싱합니다."""
    raw = pd.read_excel(io.BytesIO(file_bytes), header=None, engine="openpyxl")

    header_row_idx: int | None = None
    lot_col_idx: int | None = None
    process_col_idx: int | None = None
    qty_col_idx: int | None = None

    for i in range(len(raw)):
        row = raw.iloc[i]
        norm_cells = [_norm(v) if pd.notna(v) else "" for v in row]
        for j, cell in enumerate(norm_cells):
            if cell in ("LOTID", "LOT", "LOTNO", "LOT번호".upper()):
                lot_col_idx = j
            elif cell in ("공정ID".upper(), "공정".upper(), "PROCESSID", "PROCESS"):
                process_col_idx = j
            elif cell in ("투입수량".upper(), "투입".upper(), "INPUTQTY", "INPUT"):
                qty_col_idx = j
        if lot_col_idx is not None and process_col_idx is not None and qty_col_idx is not None:
            header_row_idx = i
            break

    if header_row_idx is None or lot_col_idx is None or process_col_idx is None or qty_col_idx is None:
        raise ValueError("작업일보에서 LOT/공정ID/투입수량 헤더를 찾지 못했습니다.")

    df = raw.iloc[header_row_idx + 1 :].copy()
    df = df.iloc[:, [lot_col_idx, process_col_idx, qty_col_idx]]
    df.columns = ["lot_id", "process_id", "input_qty"]

    df["lot_id"] = df["lot_id"].map(_clean_lot)
    df["process_id"] = df["process_id"].map(lambda x: str(x).strip() if pd.notna(x) else "")
    df["input_qty"] = pd.to_numeric(df["input_qty"], errors="coerce").fillna(0)

    df = df[df["lot_id"].ne("")].copy()
    df = df[df["process_id"].ne("")].copy()

    out = df[["lot_id", "process_id", "input_qty"]]
    print(f"[parse_work] shape={out.shape}")
    return out


# 사용 예시:
# with open("공장 받기.xlsx", "rb") as f:
#     df_ship = parse_shipment(f.read())
# with open("코드별 불량현황.xlsx", "rb") as f:
#     df_def = parse_defect(f.read())
