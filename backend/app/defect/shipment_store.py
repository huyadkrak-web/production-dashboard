"""공장 받기(parse_shipment) 데이터 누적 저장 (Supabase)."""

from __future__ import annotations

from collections import Counter

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


def _shipment_identity_tuple(row: dict) -> tuple[str, str, str, int]:
    """(이동일자, LOT, 제품, 수량) — 동일 출하 재업로드 판별용."""
    n = _to_shipment_row(row) if row else {}
    if not n:
        return ("", "", "", 0)
    md = str(n.get("move_date", "")).strip()[:10]
    lid = str(n.get("lot_id", "")).strip()
    prod = str(n.get("product", "")).strip()
    qty = int(pd.to_numeric(n.get("move_qty"), errors="coerce") or 0)
    return (md, lid, prod, qty)


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

    # 출하 "Lot N건"은 엑셀 데이터 행 수(동일 LOT 다중 행 유지)와 맞춤
    lot_count = int(len(sdf))
    total_qty = int(pd.to_numeric(sdf.get("move_qty"), errors="coerce").fillna(0).sum())
    return {
        "min_date": min_date,
        "max_date": max_date,
        "lot_count": lot_count,
        "total_qty": total_qty,
    }


def save_shipment(df: pd.DataFrame) -> dict | None:
    """``parse_shipment`` 결과를 Supabase ``shipment`` 테이블에 누적 저장합니다."""
    new_rows = _df_to_shipment_records(df)
    if not new_rows:
        return get_shipment_summary()

    existing = load_shipment()
    new_counter: Counter[tuple[str, str, str, int]] = Counter()
    for r in new_rows:
        t = _shipment_identity_tuple(r)
        if t[0] and t[1]:
            new_counter[t] += 1

    exist_counter: Counter[tuple[str, str, str, int]] = Counter()
    for r in existing:
        t = _shipment_identity_tuple(r)
        if t[0] and t[1]:
            exist_counter[t] += 1

    if new_counter and all(exist_counter.get(k, 0) >= v for k, v in new_counter.items()):
        print("[shipment] skipped duplicate upload (identical rows already in DB)")
        summary = _build_shipment_summary(existing)
        if summary is None:
            summary = {"min_date": "", "max_date": "", "lot_count": 0, "total_qty": 0}
        summary = {**summary, "duplicate_skipped": True}
        return summary

    for row in new_rows:
        supabase_delete_by_filters(
            "shipment",
            {
                "move_date": str(row["move_date"]),
                "lot_id": str(row["lot_id"]),
                "product": str(row["product"]),
            },
        )
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


def get_shipment_move_date_rollups() -> list[dict[str, int | str]]:
    """이동일자별 출하 행 수·수량 합계(날짜 오름차순). ``move_date``(엑셀 이동일자) 기준·업로드 순과 무관."""
    records = load_shipment()
    if not records:
        return []
    acc: dict[str, list[int]] = {}
    for r in records:
        raw = r.get("move_date")
        ts = pd.to_datetime(raw, errors="coerce")
        if pd.isna(ts):
            continue
        d = ts.strftime("%Y-%m-%d")
        q = int(pd.to_numeric(r.get("move_qty"), errors="coerce") or 0)
        if d not in acc:
            acc[d] = [0, 0]
        acc[d][0] += 1
        acc[d][1] += q
    out: list[dict[str, int | str]] = []
    for d in sorted(acc.keys()):
        rc, tq = acc[d]
        out.append({"date": d, "row_count": rc, "total_qty": tq})
    return out


def clear_shipment() -> None:
    """Supabase ``shipment`` 테이블 데이터를 전체 삭제합니다."""
    supabase_delete_all("shipment")
    print("[shipment] cleared")
