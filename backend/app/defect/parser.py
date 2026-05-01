"""엑셀 출하·불량 파일을 DataFrame으로 파싱합니다."""

from __future__ import annotations

import io
import json
import logging
import re
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# 출하(공장 받기) 엑셀: 다중 시트 시 이 이름이 있으면 우선 사용
_SHIPMENT_SHEET_PREFERRED = "공장 받기@2"

# 헤더 탐색 시 상단 몇 행까지 볼지 (이동일자·타이틀 행 포함)
_SHIPMENT_HEADER_SCAN_ROWS = 55

_RESERVED_LOT_TOKENS = frozenset(
    {
        "LOTID",
        "LOT",
        "LOTNO",
        "LOT번호",
        "부모LOTID",
        "LOTID.",
    }
)
_RESERVED_PRODUCT_TOKENS = frozenset(
    {
        "제품ID",
        "제품 ID",
        "PRODUCTID",
        "PRODUCT",
        "품목ID",
        "품목 ID",
        "품목명",
        "품목",
    }
)
_SUMMARY_HINTS = re.compile(
    r"(합계|총계|소계|합\s*산|grand\s*total|sub\s*total|total)",
    re.IGNORECASE,
)


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
    return str(x).strip().replace(" ", "").replace("\n", "").replace("\u3000", "").upper()


def _norm_key_cell(x: Any) -> str:
    return _norm(x) if pd.notna(x) else ""


def _is_reserved_lot_value(lot: str) -> bool:
    n = _norm_key_cell(lot)
    if not n:
        return False
    if n in _RESERVED_LOT_TOKENS:
        return True
    if n == "LOTID" or n.startswith("LOTID"):
        return True
    return False


def _is_reserved_product_value(product: str) -> bool:
    raw = str(product).strip() if pd.notna(product) else ""
    if raw in _RESERVED_PRODUCT_TOKENS:
        return True
    return _norm_key_cell(product) in {_norm_key_cell(x) for x in _RESERVED_PRODUCT_TOKENS}


def _is_summary_label(text: str) -> bool:
    s = str(text).strip()
    if not s:
        return False
    return bool(_SUMMARY_HINTS.search(s))


def _matches_lot_header_cell(v: Any) -> bool:
    if pd.isna(v):
        return False
    n = _norm_key_cell(v)
    if not n:
        return False
    if n in _RESERVED_LOT_TOKENS:
        return True
    if "LOT" in n and "ID" in n and len(n) <= 24:
        return True
    return False


def _matches_total_qty_header(v: Any) -> tuple[bool, int]:
    """총 수량 열 우선. (매칭 여부, 우선순위 0=최우선)."""
    if pd.isna(v):
        return False, 99
    raw = str(v).strip()
    n = _norm_key_cell(v)
    if n == "총수량":
        return True, 0
    if "총" in raw and "수량" in raw and "이동" not in raw:
        return True, 1
    return False, 99


def _matches_move_qty_header(v: Any) -> bool:
    if pd.isna(v):
        return False
    return _norm_key_cell(v) == "이동수량"


def _matches_move_date_header(v: Any) -> bool:
    if pd.isna(v):
        return False
    n = _norm_key_cell(v)
    raw = str(v).strip()
    if n == "이동일자":
        return True
    return "이동일자" in raw


def _matches_product_header(v: Any) -> bool:
    if pd.isna(v):
        return False
    n = _norm_key_cell(v)
    raw = str(v).strip()
    if raw in _RESERVED_PRODUCT_TOKENS:
        return True
    if n in ("제품ID", "품목ID", "품목명", "PRODUCTID"):
        return True
    return False


def _find_shipment_header_and_columns(
    raw: pd.DataFrame,
) -> tuple[int, int, int | None, int, int | None, str]:
    """(header_row_idx, lot_col, product_col|None, qty_col, move_date_col|None, mode_desc)."""
    max_r = min(_SHIPMENT_HEADER_SCAN_ROWS, len(raw))
    best: tuple[int, int, int | None, int, int | None, str] | None = None

    for i in range(max_r):
        row = raw.iloc[i]
        lot_j: int | None = None
        prod_j: int | None = None
        date_j: int | None = None
        qty_candidates: list[tuple[int, int, int]] = []  # (priority, col, score)

        for j, v in enumerate(row):
            if lot_j is None and _matches_lot_header_cell(v):
                lot_j = j
            if prod_j is None and _matches_product_header(v):
                prod_j = j
            if date_j is None and _matches_move_date_header(v):
                date_j = j
            ok, pri = _matches_total_qty_header(v)
            if ok:
                qty_candidates.append((pri, 0, j))
            elif _matches_move_qty_header(v):
                qty_candidates.append((2, 1, j))

        if lot_j is None or not qty_candidates:
            continue
        qty_candidates.sort(key=lambda t: (t[0], t[1], t[2]))
        qty_j = qty_candidates[0][2]
        mode = "header_scan:총수량" if qty_candidates[0][0] < 2 else "header_scan:이동수량(총수량열없음)"
        best = (i, lot_j, prod_j, qty_j, date_j, mode)
        break

    if best is not None:
        return best[0], best[1], best[2], best[3], best[4], best[5]

    # 레거시: 7행부터, C/E/I (인덱스 2,4,8), D4 일괄 일자
    return 5, 2, 4, 8, None, "legacy_fixed_CEI"


def _read_global_move_date_from_d4(raw: pd.DataFrame) -> pd.Timestamp:
    try:
        return pd.to_datetime(raw.iloc[3, 3], errors="coerce")
    except Exception:
        return pd.NaT


def _lot_from_row_series(
    row: pd.Series, lot_col: int, span: int = 4
) -> tuple[str, str | None]:
    """LOT 열이 비었을 때 오른쪽 인접 열에서 보조 탐색. (값, 제외사유 없음)."""
    max_c = len(row)
    for j in range(lot_col, min(lot_col + span, max_c)):
        s = _clean_lot(row.iloc[j])
        if not s:
            continue
        if _is_reserved_lot_value(s):
            return "", "reserved_lot_token"
        if _is_summary_label(s):
            return "", "summary_or_label_row"
        return s, None
    return "", "empty_lot"


def parse_shipment(file_bytes: bytes) -> pd.DataFrame:
    """공장 받기.xlsx(출하): 시트 ``공장 받기@2`` 우선, 헤더 행에서 LOT·총 수량 열 탐지.

    레거시 고정(7행~, C/E/I, D4 일자)은 헤더를 찾지 못할 때만 사용합니다.
    """
    bio = io.BytesIO(file_bytes)
    xl = pd.ExcelFile(bio, engine="openpyxl")
    sheet_names = list(xl.sheet_names)
    selected_sheet_name = _select_shipment_sheet_name(sheet_names)

    raw = pd.read_excel(
        xl,
        sheet_name=selected_sheet_name,
        header=None,
        dtype=object,
    )
    original_row_count = int(len(raw))

    header_idx, lot_col, prod_col, qty_col, date_col, layout_mode = (
        _find_shipment_header_and_columns(raw)
    )
    global_move_date = _read_global_move_date_from_d4(raw)

    exclusions: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    data_start = header_idx + 1
    if layout_mode.startswith("legacy"):
        data_start = 6

    for ridx in range(data_start, len(raw)):
        excel_row_1based = ridx + 1
        row = raw.iloc[ridx]
        lot, lot_reason = _lot_from_row_series(row, lot_col, span=5)
        if prod_col is not None and prod_col < len(row):
            product = "" if pd.isna(row.iloc[prod_col]) else str(row.iloc[prod_col]).strip()
        else:
            product = ""

        qty_raw = row.iloc[qty_col] if qty_col < len(row) else pd.NA
        move_qty = pd.to_numeric(qty_raw, errors="coerce")

        if date_col is not None and date_col < len(row):
            move_date = pd.to_datetime(row.iloc[date_col], errors="coerce")
        else:
            move_date = pd.NaT
        if pd.isna(move_date):
            move_date = global_move_date

        reason_chain: list[str] = []
        if lot_reason:
            reason_chain.append(lot_reason)

        if _is_summary_label(lot) or _is_summary_label(product):
            exclusions.append(
                {
                    "excel_row": excel_row_1based,
                    "lot_id": lot,
                    "product": product,
                    "move_qty": None if pd.isna(move_qty) else float(move_qty),
                    "reason": "summary_or_label_row",
                }
            )
            continue

        if _is_reserved_lot_value(lot):
            exclusions.append(
                {
                    "excel_row": excel_row_1based,
                    "lot_id": lot,
                    "product": product,
                    "move_qty": None if pd.isna(move_qty) else float(move_qty),
                    "reason": "reserved_lot_header_token",
                }
            )
            continue

        if not lot:
            exclusions.append(
                {
                    "excel_row": excel_row_1based,
                    "lot_id": "",
                    "product": product,
                    "move_qty": None if pd.isna(move_qty) else float(move_qty),
                    "reason": "empty_lot",
                }
            )
            continue

        if _is_reserved_product_value(product):
            exclusions.append(
                {
                    "excel_row": excel_row_1based,
                    "lot_id": lot,
                    "product": product,
                    "move_qty": None if pd.isna(move_qty) else float(move_qty),
                    "reason": "reserved_product_header_token",
                }
            )
            continue

        if pd.isna(move_qty):
            exclusions.append(
                {
                    "excel_row": excel_row_1based,
                    "lot_id": lot,
                    "product": product,
                    "move_qty": None,
                    "reason": "move_qty_not_numeric",
                }
            )
            continue

        if pd.isna(move_date):
            exclusions.append(
                {
                    "excel_row": excel_row_1based,
                    "lot_id": lot,
                    "product": product,
                    "move_qty": float(move_qty),
                    "reason": "move_date_missing",
                }
            )
            continue

        records.append(
            {
                "lot_id": lot,
                "product": product,
                "move_qty": int(round(float(move_qty))),
                "move_date": move_date,
            }
        )

    out = pd.DataFrame(records)
    if out.empty:
        raise ValueError(
            "출하 시트에서 유효한 데이터 행을 찾지 못했습니다. "
            "LOT·총 수량 헤더 행과 데이터 형식을 확인하세요."
        )

    out = out[["lot_id", "product", "move_qty", "move_date"]]
    filtered_row_count = len(out)
    lot_ids = out["lot_id"].tolist()
    move_sum = int(pd.to_numeric(out["move_qty"], errors="coerce").fillna(0).sum())

    body_rows_before_filter = max(0, original_row_count - data_start)
    report = {
        "selected_sheet": selected_sheet_name,
        "sheet_names": sheet_names,
        "layout_mode": layout_mode,
        "header_row_0based": header_idx,
        "lot_col_0based": lot_col,
        "product_col_0based": prod_col,
        "qty_col_0based": qty_col,
        "move_date_col_0based": date_col,
        "sheet_total_rows": original_row_count,
        "body_row_count_before_filter": body_rows_before_filter,
        "data_start_row_0based": data_start,
        "filtered_row_count": filtered_row_count,
        "lot_id_list": lot_ids,
        "move_qty_sum": move_sum,
        "excluded_rows": exclusions,
        "lot_count_basis": "shipment_row_count(원본 출하 행, 중복 LOT 유지)",
    }
    out.attrs["shipment_parse_report"] = report

    ex_preview = exclusions if len(exclusions) <= 80 else exclusions[:80] + [
        {"note": f"... 외 {len(exclusions) - 80}건 생략"}
    ]
    logger.info(
        "[parse_shipment] %s",
        json.dumps(
            {
                "selected_sheet": selected_sheet_name,
                "sheet_total_rows": original_row_count,
                "body_row_count_before_filter": body_rows_before_filter,
                "filtered_row_count": filtered_row_count,
                "move_qty_sum": move_sum,
                "layout_mode": layout_mode,
                "excluded_count": len(exclusions),
                "excluded_rows": ex_preview,
            },
            ensure_ascii=False,
            default=str,
        ),
    )
    logger.info(
        "[parse_shipment] lot_id 목록(%d건): %s",
        len(lot_ids),
        json.dumps(lot_ids, ensure_ascii=False),
    )
    print(
        "shipment parse:",
        selected_sheet_name,
        layout_mode,
        "rows",
        filtered_row_count,
        "sum",
        move_sum,
        "excluded",
        len(exclusions),
    )
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
        raise ValueError("헤더 행에서 '부모 LOT ID' 셀을 찾지 못했습니다.")

    df = raw.iloc[header_row_idx + 1 :].copy()
    df.columns = [
        str(x).strip() if pd.notna(x) else "" for x in raw.iloc[header_row_idx]
    ]

    rename: dict[str, str] = {}
    for c in df.columns:
        key = str(c).strip() if pd.notna(c) else ""
        nk = _norm(key)
        if nk == "부모LOTID":
            rename[c] = "lot_id"
        elif nk == "불량수량":
            rename[c] = "defect_qty"
        elif nk == "불량명":
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
