"""엑셀 출하·불량 파일을 DataFrame으로 파싱합니다."""

from __future__ import annotations

import io
import json
import logging
import math
import re
from typing import Any, Iterable

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
# Excel이 긴 숫자 LOT을 float·과학표기 문자열로 바꾼 경우만 정수 문자열로 통일 (알파벳 LOT은 그대로)
_LOT_STRING_SCI_NOTATION = re.compile(r"^[+-]?\d+(\.\d+)?[eE][+-]?\d+\s*$")


def _select_shipment_sheet_name(sheet_names: list[str]) -> str:
    """시트 선택: '공장 받기@2' → 두 번째 시트 → 첫 시트."""
    if not sheet_names:
        raise ValueError("엑셀에 시트가 없습니다.")
    if _SHIPMENT_SHEET_PREFERRED in sheet_names:
        return _SHIPMENT_SHEET_PREFERRED
    if len(sheet_names) >= 2:
        return sheet_names[1]
    return sheet_names[0]


def _clean_lot(x: Any) -> str:
    """LOT 문자열 정규화. 출하·불량·작업일보 간 매칭용(Excel 숫자/과학표기·.0 접미)."""
    if pd.isna(x):
        return ""
    if isinstance(x, bool):
        return ""
    if hasattr(x, "item") and callable(getattr(x, "item", None)):
        try:
            xi = x.item()
        except Exception:
            xi = None
        if xi is not None and type(xi) is not type(x):
            return _clean_lot(xi)
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        fv = float(x)
        if not math.isfinite(fv):
            return ""
        if abs(fv - round(fv)) < 1e-9:
            return str(int(round(fv)))
        return str(x).strip()
    s = str(x).strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return ""
    if _LOT_STRING_SCI_NOTATION.match(s):
        try:
            fv = float(s)
            if math.isfinite(fv) and abs(fv - round(fv)) < 1e-9:
                return str(int(round(fv)))
        except ValueError:
            pass
    if s.endswith(".0"):
        core = s[:-2]
        if core and core.replace("-", "").isdigit():
            return core
    # 순수 숫자 문자열만 정수 LOT으로 통일(알파벳·하이픈 LOT은 그대로)
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s) and "e" not in s.lower():
        try:
            fv = float(s)
            if math.isfinite(fv) and abs(fv - round(fv)) < 1e-9:
                return str(int(round(fv)))
        except ValueError:
            pass
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


def _find_defect_header_row(raw: pd.DataFrame) -> int | None:
    """불량수량·불량명과 함께 LOT 관련 헤더가 있는 첫 행."""
    for i in range(len(raw)):
        row = raw.iloc[i]
        norms = [_norm(v) if pd.notna(v) else "" for v in row]
        if "불량수량" not in norms or "불량명" not in norms:
            continue
        if "부모LOTID" in norms or "LOTID" in norms:
            return i
        if any("LOT" in (n or "") for n in norms):
            return i
    return None


def _lot_candidate_columns(headers: list[str]) -> list[str]:
    """헤더명에 LOT(정규화 기준)이 포함된 열. 공백 이름 제외, 안정적 순서."""
    out: list[str] = []
    seen: set[str] = set()
    for h in headers:
        key = str(h).strip() if h is not None else ""
        if not key or key in seen:
            continue
        if "LOT" in _norm(key):
            seen.add(key)
            out.append(key)
    return sorted(out, key=lambda c: _norm(c))


def _column_by_norm(headers: Iterable[str], target_norm: str) -> str | None:
    for c in headers:
        key = str(c).strip() if c is not None else ""
        if _norm(key) == target_norm:
            return key
    return None


def parse_defect(
    file_bytes: bytes,
    shipment_lot_ids: frozenset[str] | set[str] | None = None,
) -> pd.DataFrame:
    """코드별 불량현황.xlsx: 헤더 자동 탐지 후 LOT·불량수량·불량명 매핑.

    ``shipment_lot_ids``가 주어지면 LOT 이름에 'LOT'이 포함된 열마다 출하 LOT과 교집합을 계산하고,
    교집합이 가장 큰 열을 ``lot_id``로 사용한다(동률이면 열 이름 오름차순). 모두 0이면 ``부모 LOTID`` 열을 유지한다.
    """
    raw = pd.read_excel(io.BytesIO(file_bytes), header=None, engine="openpyxl")

    header_row_idx = _find_defect_header_row(raw)
    if header_row_idx is None:
        raise ValueError(
            "헤더 행을 찾지 못했습니다. 불량수량·불량명과 함께 LOT ID 또는 부모 LOT ID 등이 있는 행인지 확인하세요."
        )

    df = raw.iloc[header_row_idx + 1 :].copy()
    df.columns = [
        str(x).strip() if pd.notna(x) else "" for x in raw.iloc[header_row_idx]
    ]

    headers_before_rename = [str(c).strip() if pd.notna(c) else "" for c in df.columns]
    lot_related_column_names = _lot_candidate_columns(headers_before_rename)

    qty_col = _column_by_norm(headers_before_rename, "불량수량")
    name_col = _column_by_norm(headers_before_rename, "불량명")
    if not qty_col or not name_col:
        raise ValueError(
            f"필수 컬럼이 없습니다: 불량수량={qty_col!r}, 불량명={name_col!r}"
        )

    ship_set = frozenset(x for x in (shipment_lot_ids or frozenset()) if x)

    candidate_stats: list[dict[str, Any]] = []
    for col in lot_related_column_names:
        if col not in df.columns:
            continue
        vals = df[col].map(_clean_lot)
        col_set = {v for v in vals.tolist() if v}
        inter_n = len(col_set & ship_set) if ship_set else 0
        sample_10 = sorted(col_set)[:10]
        row = {
            "column_name": col,
            "sample_10": sample_10,
            "intersection_count_with_shipment": inter_n,
        }
        candidate_stats.append(row)
        print(
            "[parse_defect][lot_column_candidate] "
            + json.dumps(row, ensure_ascii=False, default=str),
        )

    parent_col = _column_by_norm(headers_before_rename, "부모LOTID")
    selected_lot_col: str | None = None
    selection_reason = ""

    if not lot_related_column_names:
        raise ValueError("LOT 관련 컬럼(헤더에 LOT 포함)을 찾지 못했습니다.")

    if ship_set and candidate_stats:
        best_n = max(s["intersection_count_with_shipment"] for s in candidate_stats)
        if best_n > 0:
            tied = [s["column_name"] for s in candidate_stats if s["intersection_count_with_shipment"] == best_n]
            selected_lot_col = sorted(tied)[0]
            selection_reason = "max_intersection_with_shipment"
        else:
            selected_lot_col = parent_col if parent_col else lot_related_column_names[0]
            selection_reason = "fallback_parent_lotid_all_zero_intersection"
            print(
                "[parse_defect][WARNING] "
                + json.dumps(
                    {
                        "message": "모든 LOT 후보 열의 출하 교집합이 0입니다. 부모 LOTID(있으면)로 유지합니다.",
                        "selected_defect_lot_column": selected_lot_col,
                    },
                    ensure_ascii=False,
                ),
            )
    else:
        selected_lot_col = parent_col if parent_col else lot_related_column_names[0]
        selection_reason = (
            "no_shipment_lot_ids_passed_use_parent_or_first_lot_column"
            if not ship_set
            else "no_candidate_stats"
        )

    if not selected_lot_col or selected_lot_col not in df.columns:
        raise ValueError(f"LOT 집계 열을 결정하지 못했습니다: {selected_lot_col!r}")

    print(
        "[parse_defect][lot_column_selected] "
        + json.dumps(
            {
                "selected_defect_lot_column": selected_lot_col,
                "selection_reason": selection_reason,
            },
            ensure_ascii=False,
        ),
    )

    occurrence_col: str | None = None
    for nk in ("발생일자", "발생일", "불량발생일"):
        occurrence_col = _column_by_norm(headers_before_rename, nk)
        if occurrence_col:
            break
    process_col = _column_by_norm(headers_before_rename, "공정ID") or _column_by_norm(
        headers_before_rename, "공정"
    )

    take_cols = [selected_lot_col, qty_col, name_col]
    if occurrence_col:
        take_cols.append(occurrence_col)
    if process_col:
        take_cols.append(process_col)
    take_cols = list(dict.fromkeys(take_cols))

    out_narrow = df[take_cols].copy()
    ren = {
        selected_lot_col: "lot_id",
        qty_col: "defect_qty",
        name_col: "defect_name",
    }
    if occurrence_col:
        ren[occurrence_col] = "occurrence_date"
    if process_col:
        ren[process_col] = "process_id"
    out_narrow = out_narrow.rename(columns=ren)

    if "occurrence_date" not in out_narrow.columns:
        out_narrow["occurrence_date"] = pd.NaT
    else:
        out_narrow["occurrence_date"] = pd.to_datetime(
            out_narrow["occurrence_date"], errors="coerce"
        )
    if "process_id" not in out_narrow.columns:
        out_narrow["process_id"] = ""
    else:
        out_narrow["process_id"] = out_narrow["process_id"].map(
            lambda x: str(x).strip().upper()
            if pd.notna(x) and str(x).strip().lower() not in ("nan", "none")
            else ""
        )

    if not occurrence_col:
        print(
            "[parse_defect][WARNING] "
            + json.dumps(
                {
                    "message": "발생일자 열을 찾지 못했습니다. 주차·월별 자동 집계는 불량 발생일 기준 행이 없어 불량 합이 비게 될 수 있습니다.",
                    "tried_norm_keys": ["발생일자", "발생일", "불량발생일"],
                },
                ensure_ascii=False,
            ),
        )

    out_narrow["lot_id"] = out_narrow["lot_id"].map(_clean_lot)
    out_narrow = out_narrow[out_narrow["lot_id"].ne("")].copy()
    out_narrow["defect_qty"] = pd.to_numeric(out_narrow["defect_qty"], errors="coerce").fillna(0)

    out = out_narrow[
        ["lot_id", "defect_qty", "defect_name", "occurrence_date", "process_id"]
    ]
    lot_id_samples = sorted(out["lot_id"].unique().tolist())[:10]
    defect_set = set(out["lot_id"].tolist())
    defect_set.discard("")
    intersection_final = len(defect_set & ship_set) if ship_set else 0

    out.attrs["defect_lot_parse_report"] = {
        "all_column_names": headers_before_rename,
        "lot_related_column_names": lot_related_column_names,
        "lot_column_candidate_stats": candidate_stats,
        "selected_defect_lot_column": selected_lot_col,
        "selection_reason": selection_reason,
        "lot_id_source_column_name": selected_lot_col,
        "occurrence_date_column_name": occurrence_col or "",
        "process_id_column_name": process_col or "",
        "lot_id_samples_after_clean": lot_id_samples,
        "intersection_count_after_selection": intersection_final,
    }
    print(f"[parse_defect] shape={out.shape}")
    return out


def print_defect_shipment_lot_match_report(
    defect_df: pd.DataFrame,
    shipments: list[dict],
) -> None:
    """코드별 불량현황 헤더·LOT 컬럼·출하 LOT 교집합을 한 번에 로그 출력(매칭 규칙 변경 없음)."""
    rep = defect_df.attrs.get("defect_lot_parse_report", {})
    all_cols = rep.get("all_column_names", [])
    lot_related = rep.get("lot_related_column_names", [])
    lot_src = rep.get("lot_id_source_column_name", "")
    defect_samples = list(rep.get("lot_id_samples_after_clean", []))

    ship_lots: list[str] = []
    for s in shipments:
        if isinstance(s, dict):
            ship_lots.append(_clean_lot(s.get("lot_id")))
    ship_unique_sorted = sorted({x for x in ship_lots if x})
    ship_samples = ship_unique_sorted[:10]

    defect_set = {_clean_lot(x) for x in defect_df["lot_id"].tolist()}
    defect_set.discard("")
    ship_set = set(ship_unique_sorted)
    intersection_n = len(defect_set & ship_set)

    payload = {
        "defect_file_all_column_names": all_cols,
        "defect_file_lot_related_column_names": lot_related,
        "defect_lot_id_source_column_name": lot_src,
        "lot_column_candidate_stats": rep.get("lot_column_candidate_stats", []),
        "selected_defect_lot_column": rep.get("selected_defect_lot_column", lot_src),
        "selection_reason": rep.get("selection_reason", ""),
        "defect_lot_id_samples_10": defect_samples,
        "shipment_lot_id_samples_10": ship_samples,
        "intersection_count": intersection_n,
        "intersection_count_after_selection": rep.get("intersection_count_after_selection", intersection_n),
    }
    print(
        "[defect_auto][lot_match_diagnostics] "
        + json.dumps(payload, ensure_ascii=False, default=str),
    )


def parse_work(file_bytes: bytes) -> pd.DataFrame:
    """작업일보에서 LOT·공정(코드)·투입수량과, D/A 1차 투입 매칭용 원문(공정명·단계)을 파싱합니다."""

    raw = pd.read_excel(io.BytesIO(file_bytes), header=None, engine="openpyxl")

    _HDR_LOT = frozenset(
        {_norm("LOTID"), _norm("LOT"), _norm("LOTNO"), _norm("LOT번호"), "LOTNO", "LOT"}
    )
    _HDR_QTY = frozenset({_norm("투입수량"), _norm("투입"), "INPUTQTY", "INPUT"})

    # 공정 코드로 쓸 열 우선순위(낮을수록 우선). "공정" 단독은 이름 열과 충돌할 수 있어 마지막.
    _PROCESS_RANK: list[tuple[int, frozenset[str]]] = [
        (0, frozenset({_norm("공정ID"), "PROCESSID"})),
        (1, frozenset({_norm("공정코드"), "PROCESSCODE", _norm("OP코드"), "OPCODE"})),
        (2, frozenset({_norm("공정"), "PROCESS"})),
    ]
    _META_NAME = frozenset(
        {
            _norm("공정명"),
            _norm("공정이름"),
            "PROCESSNAME",
            "PROCESS_NAME",
            _norm("작업공정"),
            _norm("작업공정명"),
        }
    )
    _META_STEP = frozenset({_norm("단계"), _norm("단계명"), "STEP", "STAGE", _norm("공정단계")})

    header_row_idx: int | None = None
    lot_col_idx: int | None = None
    qty_col_idx: int | None = None
    process_pick: tuple[int, int] | None = None  # (rank, col_idx)
    meta_col_indices: list[int] = []

    for i in range(len(raw)):
        row = raw.iloc[i]
        norm_cells = [_norm(v) if pd.notna(v) else "" for v in row]
        lot_col_idx = None
        qty_col_idx = None
        process_pick = None
        meta_col_indices = []

        for j, cell in enumerate(norm_cells):
            if not cell:
                continue
            if cell in _HDR_LOT and lot_col_idx is None:
                lot_col_idx = j
            elif cell in _HDR_QTY and qty_col_idx is None:
                qty_col_idx = j
            else:
                for rank, headers in _PROCESS_RANK:
                    if cell in headers:
                        cand = (rank, j)
                        if process_pick is None or cand < process_pick:
                            process_pick = cand
                        break
                if cell in _META_NAME or cell in _META_STEP:
                    meta_col_indices.append(j)

        meta_col_indices = sorted(set(meta_col_indices))
        process_col_idx = process_pick[1] if process_pick is not None else None

        if lot_col_idx is not None and process_col_idx is not None and qty_col_idx is not None:
            header_row_idx = i
            break

    if header_row_idx is None or lot_col_idx is None or process_pick is None or qty_col_idx is None:
        raise ValueError("작업일보에서 LOT/공정ID/투입수량 헤더를 찾지 못했습니다.")

    process_col_idx = process_pick[1]
    proc_rank = process_pick[0]
    body = raw.iloc[header_row_idx + 1 :].copy()

    def _row_meta(parts: pd.Series) -> str:
        acc: list[str] = []
        for mj in meta_col_indices:
            v = parts.iloc[mj]
            if pd.notna(v) and str(v).strip():
                acc.append(str(v).strip())
        return " ".join(acc)

    lots = body.iloc[:, lot_col_idx].map(_clean_lot)
    pids = body.iloc[:, process_col_idx].map(
        lambda x: str(x).strip() if pd.notna(x) else "",
    )
    qtys = pd.to_numeric(body.iloc[:, qty_col_idx], errors="coerce").fillna(0)
    metas = body.apply(_row_meta, axis=1)

    out = pd.DataFrame(
        {
            "lot_id": lots,
            "process_id": pids,
            "input_qty": qtys,
            "process_meta": metas,
        }
    )

    out = out[out["lot_id"].ne("")].copy()
    out = out[
        out["process_id"].ne("") | out["process_meta"].str.strip().str.len().gt(0)
    ].copy()

    print(
        f"[parse_work] shape={out.shape} process_header_rank={proc_rank} "
        f"(0=공정ID,1=공정코드,2=공정/PROCESS) meta_cols={len(meta_col_indices)}",
    )
    return out


# 사용 예시:
# with open("공장 받기.xlsx", "rb") as f:
#     df_ship = parse_shipment(f.read())
# with open("코드별 불량현황.xlsx", "rb") as f:
#     df_def = parse_defect(f.read())
