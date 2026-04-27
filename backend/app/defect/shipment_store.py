"""공장 받기(parse_shipment) 데이터 누적 저장 (Supabase)."""

from __future__ import annotations

import pandas as pd

from ..db import supabase_delete_all, supabase_delete_by_filters, supabase_get, supabase_insert
from .calculator import get_week_label

_SHIPMENT_COLS = ["move_date", "week", "lot_id", "product", "move_qty"]


def _df_to_shipment_records(df: pd.DataFrame) -> list[dict]:
    dfc = df.copy()
    dfc["move_date"] = pd.to_datetime(dfc["move_date"], errors="coerce")
    dfc = dfc[dfc["move_date"].notna()].copy()
    dfc["week"] = dfc["move_date"].apply(get_week_label)
    dfc["move_date"] = dfc["move_date"].dt.strftime("%Y-%m-%d")
    out = dfc[["move_date", "week", "lot_id", "product", "move_qty"]].copy()
    out["move_qty"] = pd.to_numeric(out["move_qty"], errors="coerce").fillna(0).astype(int)
    out["lot_id"] = out["lot_id"].astype(str)
    out["product"] = out["product"].map(lambda x: "" if pd.isna(x) else str(x))
    return out.to_dict(orient="records")


def _to_shipment_row(row: dict) -> dict:
    move_date = pd.to_datetime(row.get("move_date"), errors="coerce")
    if pd.isna(move_date):
        return {}
    lot_id = "" if pd.isna(row.get("lot_id")) else str(row.get("lot_id")).strip()
    product = "" if pd.isna(row.get("product")) else str(row.get("product")).strip()
    qty = pd.to_numeric(row.get("move_qty"), errors="coerce")
    move_qty = float(qty) if pd.notna(qty) else 0.0
    if float(move_qty).is_integer():
        move_qty = int(move_qty)
    move_date_str = move_date.strftime("%Y-%m-%d")
    week = row.get("week")
    week_str = str(week).strip() if week is not None else ""
    if not week_str:
        week_str = get_week_label(move_date)
    return {
        "move_date": move_date_str,
        "week": week_str,
        "lot_id": lot_id,
        "product": product,
        "move_qty": move_qty,
    }


def _dedupe_by_key_keep_last(records: list[dict]) -> list[dict]:
    by_key: dict[tuple[str, str, str], dict] = {}
    for row in records:
        key = (
            str(row.get("move_date", "")).strip(),
            str(row.get("lot_id", "")).strip(),
            str(row.get("product", "")).strip(),
        )
        by_key[key] = row
    return list(by_key.values())


def _build_shipment_summary(records: list[dict]) -> dict | None:
    if not records:
        return None
    sdf = pd.DataFrame(records)
    if sdf.empty:
        return None

    move_dates = pd.to_datetime(sdf.get("move_date"), errors="coerce")
    move_dates = move_dates[move_dates.notna()]
    if move_dates.empty:
        min_date = ""
        max_date = ""
    else:
        min_date = move_dates.min().strftime("%Y-%m-%d")
        max_date = move_dates.max().strftime("%Y-%m-%d")

    lot_count = int(
        sdf.get("lot_id", pd.Series(dtype=object))
        .map(lambda x: str(x).strip() if pd.notna(x) else "")
        .replace("", pd.NA)
        .dropna()
        .nunique()
    )
    total_qty = int(pd.to_numeric(sdf.get("move_qty"), errors="coerce").fillna(0).sum())
    return {
        "min_date": min_date,
        "max_date": max_date,
        "lot_count": lot_count,
        "total_qty": total_qty,
    }


def save_shipment(df: pd.DataFrame) -> dict | None:
    """``parse_shipment`` 결과를 Supabase ``shipment`` 테이블에 누적 저장합니다."""
    new_rows = _dedupe_by_key_keep_last(_df_to_shipment_records(df))
    for row in new_rows:
        supabase_delete_by_filters(
            "shipment",
            {
                "move_date": str(row["move_date"]),
                "lot_id": str(row["lot_id"]),
                "product": str(row["product"]),
            },
        )
    if new_rows:
        supabase_insert("shipment", new_rows)
    records = load_shipment()
    print("[shipment] saved")
    return _build_shipment_summary(records)


def load_shipment() -> list[dict]:
    """저장된 출하 LOT 레코드를 Supabase에서 조회합니다."""
    raw = supabase_get("shipment")
    if not isinstance(raw, list):
        return []
    rows: list[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        normalized = _to_shipment_row(r)
        if not normalized:
            continue
        rows.append(normalized)
    data = rows
    print("[shipment] loaded")
    return data


def get_shipment_summary() -> dict | None:
    """저장된 출하 누적 요약(min/max date, lot 개수, move_qty 합계)을 반환합니다."""
    return _build_shipment_summary(load_shipment())


def clear_shipment() -> None:
    """Supabase ``shipment`` 테이블 데이터를 전체 삭제합니다."""
    supabase_delete_all("shipment")
    print("[shipment] cleared")
