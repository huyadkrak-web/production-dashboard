"""시스템 전역에서 제외하는 Sample LOT 목록과 필터 유틸."""

from __future__ import annotations

import logging
from typing import Any, Iterable

import pandas as pd

_log = logging.getLogger(__name__)

# 한 곳에서만 관리 — 계산 경로별 하드코딩 금지
EXCLUDED_SAMPLE_LOTS: frozenset[str] = frozenset(
    {
        "0QD1600G0C0A-C",
        "0QD1600H0C0B-C",
        "0QD1600I0C0C-C",
        "0QD1600J0C0D-C",
        "0QD1600K0C0E-C",
        "0QD1600L0C0F-C",
    }
)


def norm_lot_compare(val: Any) -> str:
    """제외 LOT 비교용: trim + upper (값 단위)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip().upper()


EXCLUDED_SAMPLE_LOT_KEYS: frozenset[str] = frozenset(
    norm_lot_compare(x) for x in EXCLUDED_SAMPLE_LOTS
)


def is_excluded_sample_lot(val: Any) -> bool:
    k = norm_lot_compare(val)
    return bool(k) and k in EXCLUDED_SAMPLE_LOT_KEYS


def _log_excluded(context: str, removed_rows: int, removed_lot_ids: list[str]) -> None:
    uniq = sorted(set(removed_lot_ids))
    line = (
        f"[excluded_sample_lot] context={context} removed_rows={removed_rows} "
        f"removed_lot_ids={uniq}"
    )
    _log.info(line)
    print(line)


def filter_shipment_dict_rows(
    rows: list[dict[str, Any]],
    *,
    context: str,
) -> list[dict[str, Any]]:
    """출하 레코드(dict)에서 제외 LOT 행 제거."""
    if not rows:
        return rows
    kept: list[dict[str, Any]] = []
    removed_lot_ids: list[str] = []
    removed_rows = 0
    for r in rows:
        if not isinstance(r, dict):
            kept.append(r)
            continue
        lid = r.get("lot_id")
        if is_excluded_sample_lot(lid):
            removed_rows += 1
            removed_lot_ids.append(norm_lot_compare(lid))
            continue
        kept.append(r)
    if removed_rows:
        _log_excluded(context, removed_rows, removed_lot_ids)
    return kept


def filter_parse_work_dataframe(
    df: pd.DataFrame,
    *,
    context: str,
) -> pd.DataFrame:
    """parse_work 결과: ``lot_id`` 기준 제외."""
    if df.empty or "lot_id" not in df.columns:
        return df
    keys = EXCLUDED_SAMPLE_LOT_KEYS
    nl = df["lot_id"].map(norm_lot_compare)
    bad = nl.isin(keys)
    n_removed = int(bad.sum())
    if n_removed:
        removed_ids = sorted({norm_lot_compare(v) for v in df.loc[bad, "lot_id"].tolist()})
        _log_excluded(context, n_removed, removed_ids)
    return df.loc[~bad].copy()


def filter_defect_dataframe(
    df: pd.DataFrame,
    *,
    context: str,
) -> pd.DataFrame:
    """불량 파싱 DF: ``lot_id`` / ``parent_lot_id``(있으면) 중 하나라도 제외 LOT이면 행 제거."""
    if df.empty:
        return df
    keys = EXCLUDED_SAMPLE_LOT_KEYS
    mask_bad = pd.Series(False, index=df.index)
    checked_cols: list[str] = []
    for col in ("lot_id", "parent_lot_id"):
        if col not in df.columns:
            continue
        checked_cols.append(col)
        mask_bad = mask_bad | df[col].map(norm_lot_compare).isin(keys)
    if not checked_cols:
        return df
    n_removed = int(mask_bad.sum())
    if n_removed:
        removed_ids: list[str] = []
        for col in checked_cols:
            removed_ids.extend(
                norm_lot_compare(v)
                for v in df.loc[mask_bad, col].tolist()
                if norm_lot_compare(v) in keys
            )
        _log_excluded(context, n_removed, removed_ids)
    return df.loc[~mask_bad].copy()


def _header_norm_for_lot_column(name: str) -> str:
    return (
        str(name)
        .strip()
        .replace(" ", "")
        .replace("\n", "")
        .replace("\u3000", "")
        .upper()
    )


def iter_work_sheet_lot_like_columns(columns: Iterable[Any]) -> list[str]:
    """작업일보 원본/전처리 DF에서 LOT·부모 LOT 값이 들어 있는 열 이름 목록."""
    cols_list = [str(c).strip() for c in columns if c is not None and str(c).strip()]
    out: list[str] = []
    seen: set[str] = set()
    for raw in cols_list:
        if raw in seen:
            continue
        nn = _header_norm_for_lot_column(raw)
        if "LOT" not in nn:
            continue
        if nn in ("LOT수", "LOT개수", "LOT건수"):
            continue

        ok = False
        if nn in ("LOTID", "LOT", "LOTNO", "LOT번호"):
            ok = True
        elif "부모" in nn and "LOT" in nn:
            ok = True
        elif nn.startswith("PARENT") and "LOT" in nn:
            ok = True
        elif nn.startswith("SOURCE") and "LOT" in nn:
            ok = True
        elif "출하" in nn and "LOT" in nn:
            ok = True
        elif "SHIPMENT" in nn and "LOT" in nn:
            ok = True
        elif "LOTID" in nn:
            ok = True

        if ok:
            seen.add(raw)
            out.append(raw)
    return out


def filter_shipment_dataframe(
    df: pd.DataFrame,
    *,
    context: str,
) -> pd.DataFrame:
    """출하 형태 DF(``lot_id``)에서 제외 LOT 행 제거."""
    if df.empty or "lot_id" not in df.columns:
        return df
    keys = EXCLUDED_SAMPLE_LOT_KEYS
    nl = df["lot_id"].map(norm_lot_compare)
    bad = nl.isin(keys)
    n_removed = int(bad.sum())
    if n_removed:
        removed_ids = sorted({norm_lot_compare(v) for v in df.loc[bad, "lot_id"].tolist()})
        _log_excluded(context, n_removed, removed_ids)
    return df.loc[~bad].copy()


def filter_compute_work_dataframe(
    df: pd.DataFrame,
    *,
    context: str,
) -> pd.DataFrame:
    """생산일보 compute용 작업일보 DF: LOT·부모 LOT 열 값이 제외 LOT인 행 제거."""
    if df.empty:
        return df
    lot_cols = iter_work_sheet_lot_like_columns(df.columns)
    if not lot_cols:
        return df
    keys = EXCLUDED_SAMPLE_LOT_KEYS
    mask_bad = pd.Series(False, index=df.index)
    for c in lot_cols:
        mask_bad = mask_bad | df[c].map(norm_lot_compare).isin(keys)
    n_removed = int(mask_bad.sum())
    if n_removed:
        removed_ids: list[str] = []
        for c in lot_cols:
            removed_ids.extend(
                norm_lot_compare(v)
                for v in df.loc[mask_bad, c].tolist()
                if norm_lot_compare(v) in keys
            )
        _log_excluded(context, n_removed, removed_ids)
    return df.loc[~mask_bad].copy()


def apply_defect_automation_filters(
    shipments: list[dict[str, Any]],
    defect_df: pd.DataFrame,
    work_df: pd.DataFrame,
    *,
    context: str,
) -> tuple[list[dict[str, Any]], pd.DataFrame, pd.DataFrame]:
    """공정불량 자동화(주/월/LOT PPM) 계산 직전 공통 입력 필터."""
    ship_f = filter_shipment_dict_rows(shipments, context=f"{context}.shipments")
    defect_f = filter_defect_dataframe(defect_df.copy(), context=f"{context}.defect")
    work_f = filter_parse_work_dataframe(work_df.copy(), context=f"{context}.work_parse")
    return ship_f, defect_f, work_f
