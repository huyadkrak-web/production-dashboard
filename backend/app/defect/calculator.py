"""출하·불량 DataFrame을 주차별로 집계합니다."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _normalize_defect_name(x):
    if pd.isna(x):
        return "기타"
    s = str(x).strip().lower()
    return s


_DEFECT_NAME_CANONICAL = {
    "chip crack": "Chip Crack",
    "pkg broken": "PKG Broken",
    "단자 scratch": "단자 Scratch",
    "부풀음": "부풀음",
}


def _prepare_defect_df(defect_df: pd.DataFrame) -> pd.DataFrame:
    defect = defect_df.copy()
    defect["defect_name"] = defect["defect_name"].map(_normalize_defect_name)
    defect["defect_name"] = defect["defect_name"].map(
        lambda x: _DEFECT_NAME_CANONICAL.get(x, x)
    )
    return defect


def _prepare_work_df(work_df: pd.DataFrame) -> pd.DataFrame:
    work = work_df.copy()
    work["lot_id"] = work["lot_id"].map(
        lambda x: str(x).strip() if pd.notna(x) else ""
    )
    work["process_id"] = work["process_id"].map(
        lambda x: str(x).strip().upper() if pd.notna(x) else ""
    )
    work["input_qty"] = pd.to_numeric(work["input_qty"], errors="coerce").fillna(0)
    work = work[work["lot_id"].ne("")].copy()
    work = work[work["process_id"].ne("")].copy()
    return work


def _total_ppm(defect_total: int, ao_qty: int) -> float:
    return (
        0.0
        if ao_qty == 0
        else round((defect_total / ao_qty) * 1_000_000, 2)
    )


def _aggregate_by_week(
    ship: pd.DataFrame,
    defect: pd.DataFrame,
    work: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for week, grp in ship.groupby("week", sort=True):
        lot_ids = grp["lot_id"].unique().tolist()
        if work is None:
            ao_qty = int(pd.to_numeric(grp["move_qty"], errors="coerce").fillna(0).sum())
        else:
            w_week = work[
                work["lot_id"].isin(lot_ids) & work["process_id"].isin(("FDA01", "D/A"))
            ]
            ao_qty = int(pd.to_numeric(w_week["input_qty"], errors="coerce").fillna(0).sum())

        d_week = defect[defect["lot_id"].isin(lot_ids)]
        by_name = d_week.groupby("defect_name", dropna=False)["defect_qty"].sum()
        defect_total = int(pd.to_numeric(by_name, errors="coerce").fillna(0).sum())

        total_ppm = _total_ppm(defect_total, ao_qty)

        defects: list[dict[str, Any]] = []
        for name, qty in by_name.items():
            label = "" if pd.isna(name) else str(name)
            defects.append({"name": label, "count": int(qty)})

        print(
            f"[compute_weekly_defect] week={week} "
            f"ao_qty={ao_qty} defect_total={defect_total} "
            f"total_ppm={total_ppm} "
            f"defect_kinds={len(defects)} lots={len(lot_ids)}"
        )

        out.append(
            {
                "week": week,
                "ao_qty": ao_qty,
                "defect_total": defect_total,
                "total_ppm": total_ppm,
                "defects": defects,
            }
        )

    return out


def get_week_label(date: pd.Timestamp) -> str:
    """ISO 8601 주차 번호를 ``WWxx`` 형태 문자열로 반환합니다.

    Parameters
    ----------
    date:
        기준일(시각). ``pandas.Timestamp`` 또는 이로 변환 가능한 스칼라.

    Returns
    -------
    str
        예: 16주 → ``\"WW16\"``.
    """
    ts = pd.Timestamp(date)
    week_no = int(ts.isocalendar().week)
    return f"WW{week_no:02d}"


def get_month_label(date: pd.Timestamp) -> str:
    """``move_date`` 기준 월 라벨 ``YY.M`` (예: 2026-04-25 → ``\"26.4\"``)."""
    ts = pd.Timestamp(date)
    yy = int(ts.year) % 100
    mon = int(ts.month)
    return f"{yy}.{mon}"


def _shipments_df_from_list(shipments: list[dict]) -> pd.DataFrame:
    """출하 dict 목록을 ``lot_id`` / ``product`` / ``move_qty`` / ``move_date`` 정규화 DF로 만듭니다."""
    ship = pd.DataFrame(shipments)

    if "lot_id" not in ship.columns:
        ship["lot_id"] = ""
    else:
        ship["lot_id"] = ship["lot_id"].map(
            lambda x: str(x).strip() if pd.notna(x) else ""
        )

    if "product" not in ship.columns:
        ship["product"] = ""
    else:
        ship["product"] = ship["product"].map(
            lambda x: str(x).strip() if pd.notna(x) else ""
        )

    if "move_qty" not in ship.columns:
        ship["move_qty"] = 0
    else:
        ship["move_qty"] = pd.to_numeric(
            ship["move_qty"], errors="coerce"
        ).fillna(0)

    ship["move_date"] = pd.to_datetime(ship["move_date"], errors="coerce")
    return ship


def _aggregate_by_month(
    ship: pd.DataFrame,
    defect: pd.DataFrame,
    work: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def _month_sort_key(label: str) -> tuple[int, int]:
        yy_s, m_s = str(label).split(".", 1)
        return (int(yy_s), int(m_s))

    grouped = list(ship.groupby("month", sort=False))
    grouped.sort(key=lambda item: _month_sort_key(str(item[0])))

    for month, grp in grouped:
        lot_ids = grp["lot_id"].unique().tolist()
        if work is None:
            ao_qty = int(pd.to_numeric(grp["move_qty"], errors="coerce").fillna(0).sum())
        else:
            w_mon = work[
                work["lot_id"].isin(lot_ids) & work["process_id"].isin(("FDA01", "D/A"))
            ]
            ao_qty = int(pd.to_numeric(w_mon["input_qty"], errors="coerce").fillna(0).sum())

        d_mon = defect[defect["lot_id"].isin(lot_ids)]
        by_name = d_mon.groupby("defect_name", dropna=False)["defect_qty"].sum()
        defect_total = int(pd.to_numeric(by_name, errors="coerce").fillna(0).sum())

        total_ppm = _total_ppm(defect_total, ao_qty)

        defects: list[dict[str, Any]] = []
        for name, qty in by_name.items():
            label = "" if pd.isna(name) else str(name)
            defects.append({"name": label, "count": int(qty)})

        print(
            f"[compute_monthly_defect_from_shipments] month={month} "
            f"ao_qty={ao_qty} defect_total={defect_total} total_ppm={total_ppm}"
        )

        out.append(
            {
                "month": month,
                "ao_qty": ao_qty,
                "defect_total": defect_total,
                "total_ppm": total_ppm,
                "defects": defects,
            }
        )

    return out


def compute_weekly_defect(
    shipment_df: pd.DataFrame,
    defect_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """출하 ``shipment_df``의 주차별 이동수량과, 해당 주에 포함된 LOT의 불량 건수를 집계합니다.

    ``shipment_df``는 ``parse_shipment`` 결과(``move_date``, ``lot_id``, ``move_qty`` 등),
    ``defect_df``는 ``parse_defect`` 결과(``lot_id``, ``defect_qty``, ``defect_name``)를
    가정합니다. 불량은 출하에 등장한 ``lot_id``와 정확히 일치하는 행만 포함합니다.

    Parameters
    ----------
    shipment_df:
        출하 데이터.
    defect_df:
        불량 데이터.

    Returns
    -------
    list[dict[str, Any]]
        주차별 ``week``, ``ao_qty``, ``defect_total``, ``total_ppm``, ``defects`` 목록.
    """
    ship = shipment_df.copy()
    before = len(ship)
    ship = ship[ship["move_date"].notna()].copy()
    removed = before - len(ship)
    if removed:
        print(f"[compute_weekly_defect] removed rows with empty move_date: {removed}")

    ship["week"] = ship["move_date"].apply(get_week_label)

    defect = _prepare_defect_df(defect_df)
    return _aggregate_by_week(ship, defect)


def compute_weekly_defect_from_shipments(
    shipments: list[dict],
    defect_df: pd.DataFrame,
    work_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """``shipment_lots.json`` 등에서 불러온 출하 레코드로 주차별 불량을 집계합니다.

    ``shipments``는 ``move_date``, ``lot_id``, ``product``, ``move_qty`` 키를 가진
    dict 목록(``load_shipment`` 결과 형태)을 가정합니다. ``week``가 비어 있으면
    ``move_date``로부터 ``get_week_label``을 적용합니다.

    Parameters
    ----------
    shipments:
        누적 출하 JSON에서 읽은 레코드 목록.
    defect_df:
        ``parse_defect`` 결과와 동일한 컬럼을 가진 불량 데이터.
    work_df:
        ``parse_work`` 결과와 동일한 컬럼(LOT/공정ID/투입수량) 데이터.

    Returns
    -------
    list[dict[str, Any]]
        ``compute_weekly_defect``와 동일한 주차별 구조.
    """
    if not shipments:
        return []

    ship = _shipments_df_from_list(shipments)

    if "week" not in ship.columns:
        ship["week"] = pd.Series(pd.NA, index=ship.index, dtype=object)
        m_date_ok = ship["move_date"].notna()
        ship.loc[m_date_ok, "week"] = ship.loc[m_date_ok, "move_date"].apply(
            get_week_label
        )
    else:
        w_raw = ship["week"]
        w_str = w_raw.astype(str).str.strip()
        missing_week = w_raw.isna() | w_str.eq("") | w_str.str.lower().isin(
            ("nan", "none")
        )
        ship["week"] = w_str
        m_fill = missing_week & ship["move_date"].notna()
        ship.loc[m_fill, "week"] = ship.loc[m_fill, "move_date"].apply(get_week_label)

    before = len(ship)
    ship = ship[ship["move_date"].notna()].copy()
    removed = before - len(ship)
    if removed:
        print(
            f"[compute_weekly_defect_from_shipments] "
            f"removed rows with empty move_date: {removed}"
        )

    ship = ship[ship["lot_id"].ne("")].copy()

    defect = _prepare_defect_df(defect_df)
    work = _prepare_work_df(work_df)
    return _aggregate_by_week(ship, defect, work)


def compute_monthly_defect_from_shipments(
    shipments: list[dict],
    defect_df: pd.DataFrame,
    work_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """누적 출하와 불량 데이터로 월별 조립 불량율(건수·PPM)을 집계합니다.

    ``shipments``는 ``move_date``, ``lot_id``, ``product``, ``move_qty`` 키를 가진
    dict 목록을 가정합니다. ``month``는 ``move_date``에서 ``YY.M`` 형식으로 생성됩니다.

    Parameters
    ----------
    shipments:
        누적 출하 레코드 목록.
    defect_df:
        ``parse_defect`` 결과와 동일한 컬럼을 가진 불량 데이터.
    work_df:
        ``parse_work`` 결과와 동일한 컬럼(LOT/공정ID/투입수량) 데이터.

    Returns
    -------
    list[dict[str, Any]]
        월별 ``month``, ``ao_qty``, ``defect_total``, ``total_ppm``, ``defects`` 목록.
    """
    if not shipments:
        return []

    ship = _shipments_df_from_list(shipments)

    before = len(ship)
    ship = ship[ship["move_date"].notna()].copy()
    removed = before - len(ship)
    if removed:
        print(
            f"[compute_monthly_defect_from_shipments] "
            f"removed rows with empty move_date: {removed}"
        )

    ship = ship[ship["lot_id"].ne("")].copy()

    ship["month"] = ship["move_date"].apply(get_month_label)

    defect = _prepare_defect_df(defect_df)
    work = _prepare_work_df(work_df)
    return _aggregate_by_month(ship, defect, work)


def compute_lot_defect_ppm_from_shipments(
    shipments: list[dict],
    defect_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """출하 LOT 기준으로 불량 건수/PPM을 집계합니다(공정 미분리)."""
    if not shipments:
        return []

    ship = _shipments_df_from_list(shipments)
    ship["_order"] = range(len(ship))
    ship = ship[ship["move_date"].notna()].copy()
    ship = ship[ship["lot_id"].ne("")].copy()
    if ship.empty:
        return []

    ship_agg = (
        ship.groupby("lot_id", dropna=False)
        .agg(
            move_date=("move_date", "min"),
            move_qty=("move_qty", "sum"),
            _order=("_order", "min"),
        )
        .reset_index()
    )
    ship_agg = ship_agg.sort_values(
        by=["move_date", "_order", "lot_id"], ascending=[True, True, True]
    )

    defect = _prepare_defect_df(defect_df)
    defect["lot_id"] = defect["lot_id"].map(
        lambda x: str(x).strip() if pd.notna(x) else ""
    )
    defect = defect[defect["lot_id"].ne("")].copy()

    lot_defect_map: dict[str, dict[str, float]] = {}
    if not defect.empty:
        g = defect.groupby(["lot_id", "defect_name"], dropna=False)["defect_qty"].sum()
        for (lot_id, defect_name), qty in g.items():
            lot_key = str(lot_id).strip()
            if not lot_key:
                continue
            by_name = lot_defect_map.setdefault(lot_key, {})
            label = "" if pd.isna(defect_name) else str(defect_name)
            by_name[label] = float(qty)

    out: list[dict[str, Any]] = []
    for _, row in ship_agg.iterrows():
        lot_id = str(row["lot_id"]).strip()
        move_date = pd.Timestamp(row["move_date"]).strftime("%Y-%m-%d")
        move_qty = float(pd.to_numeric(row["move_qty"], errors="coerce") or 0)
        move_qty_out: int | float = int(move_qty) if move_qty.is_integer() else round(move_qty, 4)

        by_name = lot_defect_map.get(lot_id, {})
        defects: list[dict[str, Any]] = []
        defect_total = 0.0
        for name in sorted(by_name.keys(), key=lambda x: str(x)):
            count = float(by_name[name])
            defect_total += count
            ppm = 0.0 if move_qty <= 0 else round((count / move_qty) * 1_000_000, 1)
            defects.append(
                {
                    "name": name,
                    "count": int(count) if count.is_integer() else round(count, 4),
                    "ppm": ppm,
                }
            )

        total_ppm = 0.0 if move_qty <= 0 else round((defect_total / move_qty) * 1_000_000, 1)
        out.append(
            {
                "lot_id": lot_id,
                "move_date": move_date,
                "move_qty": move_qty_out,
                "defect_total": int(defect_total)
                if defect_total.is_integer()
                else round(defect_total, 4),
                "total_ppm": total_ppm,
                "defects": defects,
            }
        )

    return out


# 간단한 테스트 (주석):
# from app.defect.parser import parse_defect, parse_shipment
# from pathlib import Path
# ship_b = Path("공장 받기.xlsx").read_bytes()
# def_b = Path("코드별 불량현황.xlsx").read_bytes()
# shipment_df = parse_shipment(ship_b)
# defect_df = parse_defect(def_b)
# weekly = compute_weekly_defect(shipment_df, defect_df)
# print(weekly)
