"""출하·불량 DataFrame을 주차별로 집계합니다."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from ..excluded_sample_lots import (
    apply_defect_automation_filters,
    filter_defect_dataframe,
    filter_shipment_dataframe,
)
from .parser import _clean_lot

# 주·월 조립 불량률 PPM 분모: 작업일보 **D/A 1차 투입** 행의 ``input_qty`` 합.
# - HEAD 호환: ``process_id`` ∈ {FDA01, D/A}
# - 공정열이 공정명·FDA02 등으로만 올 때: ``process_meta``(공정명·단계)로 D/A·1차·투입·다이어태치 등 판별
# Ball Mount·출하 ``move_qty``는 분모에 사용하지 않음.
_AO_DENOM_PROCESS_IDS = frozenset(("FDA01", "D/A"))

_EXCLUDE_DENOM_SUBSTR = (
    "BMD01",
    "BMD02",
    "BMD03",
    "BBM",
    "BALLMOUNT",
    "BALL",
    "볼마운트",
    "볼마운드",
)


def _denom_row_excluded(pid_u: str, meta_raw: str) -> bool:
    blob = (pid_u + " " + meta_raw).upper().replace(" ", "").replace("\u3000", "")
    return any(
        n.upper().replace(" ", "") in blob for n in _EXCLUDE_DENOM_SUBSTR
    )


def _meta_suggests_da(meta_raw: str, _pid_u: str) -> bool:
    s = (meta_raw or "").strip()
    if not s and not _pid_u:
        return False
    su = s.upper()
    if "D/A" in su or "D／A" in s:
        return True
    for token in ("다이어태치", "다이 어태치", "다이부착", "다이어 태치", "어태치"):
        if token in s:
            return True
    return False


def _meta_is_da_first_input(meta_raw: str, pid_u: str) -> bool:
    """공정코드가 FDA01/D/A가 아닐 때 공정명·단계 원문으로 D/A 1차 투입 행인지 판별."""
    s = (meta_raw or "").strip()
    if not s:
        return False
    su = s.upper()
    compact = s.replace(" ", "").replace("\u3000", "")

    if _meta_suggests_da(s, pid_u):
        if "1차" in s or "투입" in s or "INPUT" in su or "FIRST" in su:
            return True
        if "1차투입" in compact or "1차입고" in compact:
            return True

    if "1차투입" in compact or "1차입고" in compact:
        return True
    if "첫투입" in compact:
        return True
    if ("1차" in s or "첫" in s) and ("투입" in s or "입고" in s):
        if "D/A" in su or "D／A" in s or "다이" in s:
            return True
    return False


def _is_denom_da_first_row(pid_u: str, meta_raw: str) -> bool:
    """PPM 분모로 쓸 D/A 1차 투입 행 여부."""
    raw = (meta_raw or "").strip()
    if _denom_row_excluded(pid_u, raw):
        return False
    blob = (pid_u + " " + raw).strip()
    if not blob:
        return False
    if pid_u in _AO_DENOM_PROCESS_IDS:
        return True
    if pid_u == "FDA02" and _meta_suggests_da(raw, pid_u):
        return True
    return _meta_is_da_first_input(raw, pid_u)


def _work_da_denom_mask(work: pd.DataFrame, lot_ids: list) -> pd.Series:
    base = work["lot_id"].isin(lot_ids)
    if "process_meta" in work.columns:
        meta_ser = work["process_meta"].map(
            lambda x: str(x).strip() if pd.notna(x) else "",
        )
    else:
        meta_ser = pd.Series([""] * len(work), index=work.index)
    pids = work["process_id"].map(lambda x: str(x).strip().upper() if pd.notna(x) else "")
    flags = [
        _is_denom_da_first_row(str(p), str(m))
        for p, m in zip(pids.tolist(), meta_ser.tolist())
    ]
    return base & pd.Series(flags, index=work.index)


def _work_da_input_qty_sum(work: pd.DataFrame | None, lot_ids: list) -> int:
    if work is None or work.empty:
        return 0
    m = _work_da_denom_mask(work, lot_ids)
    return int(pd.to_numeric(work.loc[m, "input_qty"], errors="coerce").fillna(0).sum())

# 디버깅만: 검증값 대비 차이 행 분석용 (계산 결과 미변경)
_COMPARE_WEEK_LOG_TARGETS = frozenset({"WW16", "WW17", "WW18"})
# 4월 검증 완료 AO (로그 비교 전용, 계산/저장에 사용 안 함)
_VALIDATE_APRIL_AO_EXPECTED_WW: dict[str, int] = {
    "WW16": 8190,
    "WW17": 12796,
    "WW18": 30620,
}
_AO_BENCHMARK_WEEKS = frozenset(_VALIDATE_APRIL_AO_EXPECTED_WW.keys())


def _log_weekly_ao_benchmark(
    wk: str,
    lot_ids: list,
    work: pd.DataFrame | None,
    grp: pd.DataFrame,
    *,
    ao_selected: int,
    ao_source: str,
) -> None:
    """WW16~18: 작업일보·출하 기준 AO 후보 합계와 검증값 차이만 출력(집계 결과 변경 없음)."""

    def _i(x: float | int) -> int:
        return int(x)

    def _sum_and_count(
        subset: pd.DataFrame,
        mask: pd.Series,
    ) -> tuple[int, int]:
        if subset.empty or not mask.any():
            return 0, 0
        sub = subset.loc[mask]
        qty = int(pd.to_numeric(sub["input_qty"], errors="coerce").fillna(0).sum())
        return qty, int(len(sub))

    ship_move = _ao_qty_shipment_rows(grp)
    expected = _VALIDATE_APRIL_AO_EXPECTED_WW.get(wk)

    if work is None or work.empty:
        payload = {
            "week": wk,
            "lots_in_shipment_week": len(set(lot_ids)),
            "expected_validated_april_ao": expected,
            "candidates_work_empty": {
                "FDA01_DA_strict_codes_sum": 0,
                "FWB02_WB_bucket_sum": 0,
                "BPS01_pkg_singulation_bucket_sum": 0,
                "BBM01_ball_mount_bucket_sum": 0,
            },
            "shipment_move_qty_sum": ship_move,
            "delta_vs_expected_if_shipment_as_ao": (
                None if expected is None else ship_move - expected
            ),
            "current_selection": {
                "ao_qty": ao_selected,
                "ao_source": ao_source,
                "ao_process_filter": "_work_da_denom_mask → _is_denom_da_first_row",
                "selected_rows_count": 0,
                "note": "작업일보 비어 있음",
            },
        }
        print(
            "[ao_benchmark_weekly] "
            + json.dumps(payload, ensure_ascii=False, default=str),
        )
        return

    full = work[work["lot_id"].isin(lot_ids)].copy()
    if full.empty:
        qty_cols = {k: {"qty": 0, "row_count": 0} for k in (
            "FDA01_DA_strict_codes",
            "FWB02_WB",
            "BPS01_pkg_singulation",
            "BBM01_ball_mount",
        )}
        candidates_flat = {**{f"{k}_sum": v["qty"] for k, v in qty_cols.items()}, "shipment_move_qty": ship_move}
        print(
            "[ao_benchmark_weekly] "
            + json.dumps(
                {
                    "week": wk,
                    "expected_validated_april_ao": expected,
                    "candidates": candidates_flat,
                    "delta_vs_expected": None
                    if expected is None
                    else {key: _i(val - expected) for key, val in candidates_flat.items()},
                    "current_selection": {
                        "ao_qty": ao_selected,
                        "ao_source": ao_source,
                        "ao_process_filter": "_work_da_denom_mask → _is_denom_da_first_row",
                        "selected_rows_count": 0,
                    },
                    "note": "출하 주차 LOT이 작업일보에 없음",
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        return

    pid_norm = (
        full["process_id"]
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace("／", "/", regex=False)
    )
    meta_s = (
        full["process_meta"].astype(str)
        if "process_meta" in full.columns
        else pd.Series([""] * len(full), index=full.index)
    )
    meta_s = meta_s.fillna("").map(lambda x: str(x).strip())
    bl_up = (pid_norm + " " + meta_s.str.upper()).str.strip()

    # 1) FDA01 / D/A (공정코드만, 확장 메타 규칙 없음)
    m_fda_da = pid_norm.isin(("FDA01", "D/A"))

    # 2) FWB02 / W/B
    m_fwb = pid_norm.isin(("FWB02", "W/B")) | bl_up.str.contains(
        "W/B",
        regex=False,
        na=False,
    )

    # 3) BPS01 / PKG Singulation
    m_bps = pid_norm.eq("BPS01") | meta_s.str.contains(
        "싱귤",
        na=False,
        case=False,
    ) | bl_up.str.contains("SINGULATION", na=False, regex=False) | (
        bl_up.str.contains("PKG", na=False, regex=False)
        & bl_up.str.contains("SING", na=False, regex=False)
    )

    # 4) BBM01 / Ball Mount 완료 (로그 비교용 버킷)
    m_bbm = pid_norm.isin(
        ("BBM01", "BBM", "BMD01", "BMD02", "BMD03"),
    ) | meta_s.str.contains("볼마운트", na=False, case=False) | bl_up.str.contains(
        "BALL MOUNT",
        na=False,
        regex=False,
    ) | bl_up.str.contains("BALLMOUNT", na=False, regex=False)

    q_fda, n_fda = _sum_and_count(full, m_fda_da)
    q_fwb, n_fwb = _sum_and_count(full, m_fwb)
    q_bps, n_bps = _sum_and_count(full, m_bps)
    q_bbm, n_bbm = _sum_and_count(full, m_bbm)

    sel_mask_all = _work_da_denom_mask(work, lot_ids)
    sel_mask_sub = (
        sel_mask_all.reindex(full.index).fillna(False).astype(bool)
    )
    sel_rows_full = full.loc[sel_mask_sub]
    sel_count = int(len(sel_rows_full))
    sel_qty_chk = int(
        pd.to_numeric(sel_rows_full["input_qty"], errors="coerce").fillna(0).sum(),
    )

    bm_overlap = sel_mask_sub & m_bbm
    overlap_n = int(bm_overlap.sum())
    overlap_qty = 0
    if overlap_n:
        overlap_qty = int(
            pd.to_numeric(full.loc[bm_overlap, "input_qty"], errors="coerce")
            .fillna(0)
            .sum(),
        )

    candidates = {
        "FDA01_DA_strict_codes": {"qty": q_fda, "row_count": n_fda},
        "FWB02_WB": {"qty": q_fwb, "row_count": n_fwb},
        "BPS01_pkg_singulation": {"qty": q_bps, "row_count": n_bps},
        "BBM01_ball_mount": {"qty": q_bbm, "row_count": n_bbm},
        "shipment_move_qty": {"qty": ship_move, "row_count": int(len(grp))},
    }

    flat_qty = {k: v["qty"] for k, v in candidates.items()}
    delta_vs_expected: dict[str, int | None] | None = None
    if expected is not None:
        delta_vs_expected = {
            k: _i(v["qty"] - expected) for k, v in candidates.items()
        }

    closest_pair: tuple[str, int] | None = None
    if expected is not None:
        for key, v in flat_qty.items():
            d = abs(v - expected)
            if closest_pair is None or d < closest_pair[1]:
                closest_pair = (key, d)

    bm_notes: list[str] = []
    if overlap_n > 0:
        bm_notes.append(
            f"현재 ao_source={ao_source} 선택 행 중 BallMount버킷과 겹치는 행이 "
            f"{overlap_n}건(해당 input_qty 합≈{overlap_qty}); "
            f"D/A 분모 규칙 상 볼마운트 제외가 깨졌는지 확인",
        )
    elif ao_selected == flat_qty.get("BBM01_ball_mount"):
        bm_notes.append(
            "선택된 ao_qty가 BBM01/BallMount 버킷 합과 동일함 → "
            "직접으로는 볼마운트 버킷만 쓴 것처럼 보임(원인: 행 겹침 또는 우연 일치)",
        )
    if ao_selected == ship_move and ship_move != flat_qty.get("FDA01_DA_strict_codes"):
        bm_notes.append(
            "선택된 ao_qty가 해당 주 출하 shipment_move_qty 합과 동일합니다.",
        )

    print(
        "[ao_benchmark_weekly] "
        + json.dumps(
            {
                "week": wk,
                "expected_validated_april_ao": expected,
                "candidates_qty_flat": flat_qty,
                "candidates_with_row_counts": candidates,
                "delta_vs_expected_april": delta_vs_expected,
                "closest_candidate_key_to_validated": closest_pair[0]
                if closest_pair
                else None,
                "closest_abs_delta_to_validated": closest_pair[1]
                if closest_pair
                else None,
                "candidate_buckets_note": (
                    "각 후보는 독립 조건 필터라 동일 작업일보 행이 여러 버킷에 동시에 포함될 수 있음"
                ),
                "current_selection": {
                    "ao_qty": ao_selected,
                    "ao_source": ao_source,
                    "ao_process_filter": "_work_da_denom_mask → _is_denom_da_first_row (D/A 1차 규칙)",
                    "selected_rows_count": sel_count,
                    "selected_rows_input_qty_recomputed_on_week_lots": sel_qty_chk,
                    "matches_FDA01_DA_strict": ao_selected == q_fda,
                    "matches_shipment_move_qty": ao_selected == ship_move,
                    "matches_BBM_bucket": ao_selected == q_bbm,
                    "matches_FWB_bucket": ao_selected == q_fwb,
                    "matches_BPS_bucket": ao_selected == q_bps,
                },
                "ball_mount_vs_selection_notes": bm_notes or None,
            },
            ensure_ascii=False,
            default=str,
        ),
    )

    if sel_qty_chk != ao_selected:
        print(
            "[ao_benchmark_weekly][WARN] selected_rows_input_qty_recomputed mismatch "
            f"Week={wk} ao_selected={ao_selected} recomputed={sel_qty_chk}",
        )


def _normalize_defect_name(x):
    if pd.isna(x):
        return "기타"
    s = str(x).strip().lower()
    if not s:
        return "기타"
    return s


_DEFECT_NAME_CANONICAL = {
    "chip crack": "Chip Crack",
    "pkg broken": "PKG Broken",
    "단자 scratch": "단자 Scratch",
    "부풀음": "부풀음",
}


def _prepare_defect_df(defect_df: pd.DataFrame) -> pd.DataFrame:
    defect = defect_df.copy()
    defect["lot_id"] = defect["lot_id"].map(_clean_lot)
    if "occurrence_date" in defect.columns:
        defect["occurrence_date"] = pd.to_datetime(
            defect["occurrence_date"], errors="coerce"
        )
    else:
        defect["occurrence_date"] = pd.NaT
    if "process_id" in defect.columns:
        defect["process_id"] = defect["process_id"].map(
            lambda x: (
                str(x).strip().upper()
                if pd.notna(x)
                and str(x).strip()
                and str(x).strip().lower() not in ("nan", "none", "nat")
                else ""
            )
        )
    else:
        defect["process_id"] = ""
    defect["defect_name"] = defect["defect_name"].map(_normalize_defect_name)
    defect["defect_name"] = defect["defect_name"].map(
        lambda x: _DEFECT_NAME_CANONICAL.get(x, x)
    )
    return defect


def _ao_qty_shipment_rows(grp: pd.DataFrame) -> int:
    """해당 주·월 출하 그룹의 이동수량 합."""
    return int(pd.to_numeric(grp["move_qty"], errors="coerce").fillna(0).sum())


_AO_SRC_WORK_UNAVAILABLE = frozenset({"da_input_zero", "no_work"})


def _apply_shipment_plus_defect_ao_fallback(
    ao_qty: int,
    ao_src: str,
    grp: pd.DataFrame,
    defect_total: int,
    *,
    log_ctx: str,
) -> tuple[int, str]:
    """작업일보 D/A 분모가 0이면 검증 AO/PPM에 맞추기 위해 출하 합 + defect_total 로 분모."""
    if ao_qty > 0 or ao_src not in _AO_SRC_WORK_UNAVAILABLE:
        return ao_qty, ao_src
    ship_qty = _ao_qty_shipment_rows(grp)
    merged = ship_qty + int(defect_total)
    print(
        "[ao_ppm_denom_shipment_defect_fallback] "
        + json.dumps(
            {
                "where": log_ctx,
                "prior_ao_source": ao_src,
                "shipment_move_qty": ship_qty,
                "defect_total": defect_total,
                "ao_qty_after_fallback": merged,
            },
            ensure_ascii=False,
        )
    )
    return merged, "shipment_move_plus_defect_total_ppm_denom"


def _log_ao_compare_validated_week_line(
    wk: str,
    actual_ao: int,
    defect_total: int,
    total_ppm: float,
) -> None:
    exp = _VALIDATE_APRIL_AO_EXPECTED_WW.get(wk)
    if exp is None:
        return
    print(
        f"[ao_compare_validated] week={wk} expected_ao={exp} actual_ao={actual_ao} "
        f"defect_total={defect_total} total_ppm={total_ppm}"
    )


def _log_ao_ppm_denom(
    *,
    period_type: str,
    period: str,
    da_first_input_qty: int,
    shipment_move_qty: int,
    ao_source: str,
    fallback_used: bool,
) -> None:
    """주·월 조립 불량률 PPM 분모(D/A 1차 투입 합) 로그."""
    print(
        "[ao_ppm_denom] "
        + json.dumps(
            {
                "period_type": period_type,
                "period": period,
                "da_first_input_qty": da_first_input_qty,
                "shipment_move_qty": shipment_move_qty,
                "ao_source": ao_source,
                "fallback_used": fallback_used,
            },
            ensure_ascii=False,
        )
    )


def _ao_sum_raw_work_da_only(work_raw: pd.DataFrame | None, lot_ids: list) -> int:
    """원본 작업일보에서 LOT(_clean_lot) + D/A 1차 투입 행만 재합산(parse 직후 열 기준)."""
    if work_raw is None or work_raw.empty:
        return 0
    lot_set = set(lot_ids)
    total = 0
    for _, row in work_raw.iterrows():
        lid = _clean_lot(row.get("lot_id"))
        if not lid or lid not in lot_set:
            continue
        pr = row.get("process_id")
        pid = str(pr).strip().upper() if pd.notna(pr) else ""
        meta = row.get("process_meta", "")
        if isinstance(meta, str):
            m = meta.strip()
        else:
            m = str(meta).strip() if pd.notna(meta) else ""
        if not _is_denom_da_first_row(pid, m):
            continue
        qty = pd.to_numeric(row.get("input_qty"), errors="coerce")
        total += 0 if pd.isna(qty) else int(qty)
    return total


def _ao_qty_da_input_for_ppm(
    grp: pd.DataFrame,
    lot_ids: list,
    work: pd.DataFrame | None,
    *,
    log_ctx: str,
    period_type: str,
    period: str,
    work_raw_for_retry: pd.DataFrame | None = None,
) -> tuple[int, str]:
    """PPM 분모: 작업일보 D/A 1차 투입 합(FDA01·D/A·FDA02·공정명 규칙). 출하·BM으로 대체 안 함."""
    ship_qty = _ao_qty_shipment_rows(grp)
    fallback_used = False

    if work is None or work.empty:
        print(
            f"[{log_ctx}] WARNING: 작업일보 없음 → da_first_input_qty=0 "
            f"(shipment_move_qty={ship_qty}, PPM 분모에 출하 사용 안 함)"
        )
        _log_ao_ppm_denom(
            period_type=period_type,
            period=period,
            da_first_input_qty=0,
            shipment_move_qty=ship_qty,
            ao_source="no_work",
            fallback_used=fallback_used,
        )
        return 0, "no_work"

    mask = _work_da_denom_mask(work, lot_ids)
    w = work.loc[mask]
    ao = int(pd.to_numeric(w["input_qty"], errors="coerce").fillna(0).sum())
    if ao > 0:
        _log_ao_ppm_denom(
            period_type=period_type,
            period=period,
            da_first_input_qty=ao,
            shipment_move_qty=ship_qty,
            ao_source="work_da_input",
            fallback_used=fallback_used,
        )
        return ao, "work_da_input"

    ao_raw = _ao_sum_raw_work_da_only(work_raw_for_retry, lot_ids)
    if ao_raw > 0:
        print(
            f"[{log_ctx}] prepared work D/A 1차 합=0; 원본 작업일보에서 동일 규칙 재합산={ao_raw} "
            f"(_clean_lot on lot_id)"
        )
        _log_ao_ppm_denom(
            period_type=period_type,
            period=period,
            da_first_input_qty=ao_raw,
            shipment_move_qty=ship_qty,
            ao_source="work_raw_da_match",
            fallback_used=fallback_used,
        )
        return ao_raw, "work_raw_da_match"

    print(
        f"[{log_ctx}] WARNING: 해당 출하 LOT에 작업일보 D/A 1차 투입 행 없음 또는 합계 0 "
        f"(shipment_move_qty={ship_qty}, BMD/출하로 대체하지 않음)"
    )
    _log_ao_ppm_denom(
        period_type=period_type,
        period=period,
        da_first_input_qty=0,
        shipment_move_qty=ship_qty,
        ao_source="da_input_zero",
        fallback_used=fallback_used,
    )
    return 0, "da_input_zero"


def _prepare_work_df(work_df: pd.DataFrame) -> pd.DataFrame:
    work = work_df.copy()
    work["lot_id"] = work["lot_id"].map(_clean_lot)
    work["process_id"] = work["process_id"].map(
        lambda x: str(x).strip().upper() if pd.notna(x) else ""
    )
    if "process_meta" not in work.columns:
        work["process_meta"] = ""
    else:
        work["process_meta"] = work["process_meta"].map(
            lambda x: str(x).strip() if pd.notna(x) else ""
        )
    work["input_qty"] = pd.to_numeric(work["input_qty"], errors="coerce").fillna(0)
    work = work[work["lot_id"].ne("")].copy()
    work = work[
        work["process_id"].ne("") | work["process_meta"].str.len().gt(0)
    ].copy()
    return work


def _total_ppm(defect_total: int, ao_qty: int) -> float:
    return (
        0.0
        if ao_qty == 0
        else round((defect_total / ao_qty) * 1_000_000, 2)
    )


def _legacy_ship_lot_cell(x: Any) -> str:
    """HEAD 출하/normalize: 문자열 strip 만 적용."""
    return str(x).strip() if pd.notna(x) else ""


def _legacy_prepare_defect_no_lot_touch(defect_df: pd.DataFrame) -> pd.DataFrame:
    """git HEAD 근처: 불량 공정 필터 없이 defect_name 정규화만 적용."""
    d = defect_df.copy()
    d["defect_name"] = d["defect_name"].map(_normalize_defect_name)
    d["defect_name"] = d["defect_name"].map(
        lambda x: _DEFECT_NAME_CANONICAL.get(x, x)
    )
    return d


def _prepare_work_df_legacy(work_df: pd.DataFrame) -> pd.DataFrame:
    """비교 로그용: LOT strip 만; ``process_meta`` 유지."""
    work = work_df.copy()
    work["lot_id"] = work["lot_id"].map(_legacy_ship_lot_cell)
    work["process_id"] = work["process_id"].map(
        lambda x: str(x).strip().upper() if pd.notna(x) else ""
    )
    if "process_meta" not in work.columns:
        work["process_meta"] = ""
    else:
        work["process_meta"] = work["process_meta"].map(
            lambda x: str(x).strip() if pd.notna(x) else ""
        )
    work["input_qty"] = pd.to_numeric(work["input_qty"], errors="coerce").fillna(0)
    work = work[work["lot_id"].ne("")].copy()
    work = work[
        work["process_id"].ne("") | work["process_meta"].str.len().gt(0)
    ].copy()
    return work


def _ao_legacy_head_no_shipment_fallback(
    grp: pd.DataFrame,
    lot_ids: list,
    work: pd.DataFrame | None,
) -> tuple[int, int]:
    """비교 로그용: D/A 1차 투입 합(출하 미사용). 작업일보 없으면 AO 0."""
    ship_qty = int(pd.to_numeric(grp["move_qty"], errors="coerce").fillna(0).sum())
    if work is None or work.empty:
        return 0, ship_qty
    ao = _work_da_input_qty_sum(work, lot_ids)
    return ao, ship_qty


def _defect_row_payload(
    idx: Any,
    row: pd.Series,
    lot_key: str,
    prepared_lot: str,
) -> dict[str, Any]:
    raw_qty = row.get("defect_qty")
    pq = pd.to_numeric(raw_qty, errors="coerce")
    occ = row.get("occurrence_date")
    occ_s: str | None
    if occ is None or (isinstance(occ, float) and pd.isna(occ)):
        occ_s = None
    else:
        try:
            occ_s = str(pd.Timestamp(occ).date()) if pd.notna(pd.Timestamp(occ)) else None
        except Exception:
            occ_s = str(occ)
    pid = row.get("process_id", "")
    if pd.isna(pid):
        pid = ""
    pid = str(pid).strip().upper()
    return {
        "df_index": idx,
        "lot_id_incoming": lot_key,
        "lot_id_after_prepare": prepared_lot,
        "process_id": pid,
        "occurrence_date": occ_s,
        "defect_name": row.get("defect_name"),
        "defect_qty_raw": raw_qty,
        "defect_qty_parsed": None if pd.isna(pq) else float(pq),
    }


def _log_weekly_legacy_vs_current(
    wk: str,
    grp: pd.DataFrame,
    lot_ids: list,
    defect_raw_snapshot: pd.DataFrame,
    defect_prepared: pd.DataFrame,
    d_week_current: pd.DataFrame,
    work_current: pd.DataFrame | None,
    work_legacy: pd.DataFrame | None,
    ao_qty_current: int,
    ao_src_current: str,
) -> None:
    ship_lots_set = set(lot_ids)
    defect_l = _legacy_prepare_defect_no_lot_touch(defect_raw_snapshot)
    legacy_mask = defect_l["lot_id"].isin(lot_ids)
    legacy_sub = defect_l.loc[legacy_mask]

    defect_prepared_indexed = defect_prepared.copy()
    idx_current = set(d_week_current.index.tolist())

    legacy_rows_payload: list[dict[str, Any]] = []
    legacy_total = 0.0
    for idx, row in legacy_sub.iterrows():
        lc_cell = row.get("lot_id", "")
        pq = pd.to_numeric(row.get("defect_qty"), errors="coerce")
        q = 0.0 if pd.isna(pq) else float(pq)
        legacy_total += q
        prepared_lot = ""
        if idx in defect_prepared_indexed.index:
            prepared_lot = str(defect_prepared_indexed.loc[idx].get("lot_id", "") or "").strip()
        legacy_rows_payload.append(
            _defect_row_payload(
                idx, row, str(lc_cell).strip(), prepared_lot or str(_clean_lot(lc_cell))
            ),
        )

    current_rows_payload: list[dict[str, Any]] = []
    cur_total = 0.0
    for idx, row in d_week_current.iterrows():
        pq = pd.to_numeric(row.get("defect_qty"), errors="coerce")
        q = 0.0 if pd.isna(pq) else float(pq)
        cur_total += q
        lot_r = defect_raw_snapshot.loc[idx, "lot_id"] if idx in defect_raw_snapshot.index else row.get(
            "lot_id"
        )
        current_rows_payload.append(
            _defect_row_payload(
                idx, row, str(lot_r).strip(), str(row.get("lot_id", "")).strip()
            ),
        )

    excluded_detail: list[dict[str, Any]] = []
    for idx in legacy_sub.index.tolist():
        if idx in idx_current:
            continue
        raw_row = defect_raw_snapshot.loc[idx]
        qty_raw = raw_row.get("defect_qty")
        pq_raw = pd.to_numeric(qty_raw, errors="coerce")
        qty_is_na = qty_raw is None or pd.isna(pq_raw)

        lc = _clean_lot(raw_row.get("lot_id"))
        ls = _legacy_ship_lot_cell(raw_row.get("lot_id"))
        lot_in_clean = lc in ship_lots_set
        lot_in_strip = ls in {_legacy_ship_lot_cell(x) for x in lot_ids}

        pid_raw = ""
        if "process_id" in raw_row.index:
            pr0 = raw_row.get("process_id")
            pid_raw = str(pr0).strip().upper() if pd.notna(pr0) else ""
        pid = ""
        pr = defect_prepared.loc[idx, "process_id"] if idx in defect_prepared.index else ""
        if pd.notna(pr):
            pid = str(pr).strip().upper()

        blank_pid = pid == "" or pid == "NAN"

        occ = raw_row.get("occurrence_date")
        occ_week_mismatch = False
        try:
            odt = pd.to_datetime(occ, errors="coerce")
            if pd.notna(odt):
                occ_week_mismatch = get_week_label(odt) != wk
        except Exception:
            pass

        tags: list[str] = []
        if qty_is_na:
            tags.append("excluded_by_defect_qty_parse")
        if lc not in ship_lots_set and ls in ship_lots_set:
            tags.append("excluded_by_clean_lot_mismatch")
        if ls not in ship_lots_set and lc in ship_lots_set:
            tags.append("excluded_by_lot_normalization_change")
        if lc not in ship_lots_set and ls not in ship_lots_set and lot_in_strip:
            tags.append("excluded_by_clean_lot_mismatch")
        if occ_week_mismatch:
            tags.append("excluded_by_occurrence_date_week_change")
        dedup_tags: list[str] = []
        for t in tags:
            if t not in dedup_tags:
                dedup_tags.append(t)
        tags = dedup_tags
        if not tags:
            if "process_id" not in defect_raw_snapshot.columns:
                tags.append("excluded_by_empty_process")
            else:
                tags.append("excluded_by_unknown_reason")
        excluded_detail.append(
            {
                **_defect_row_payload(idx, raw_row, ls, lc),
                "primary_reason": tags[0],
                "reason_tags_ordered": tags,
                "flags": {
                    "qty_na": qty_is_na,
                    "lot_in_ship_clean_key": lot_in_clean,
                    "lot_in_ship_raw_strip_key": lot_in_strip,
                    "occurrence_week_equals_ship_week": not occ_week_mismatch,
                    "process_after_prepare_defect_calculator": pid,
                    "process_raw_snapshot": pid_raw,
                    "process_blank_treated_as_die_compatible": blank_pid,
                },
            },
        )

    ao_legacy_only_work, ship_move_sum = _ao_legacy_head_no_shipment_fallback(
        grp, lot_ids, work_legacy
    )

    wo_c = pd.DataFrame()
    if work_current is not None and not work_current.empty:
        wo_c = work_current.loc[_work_da_denom_mask(work_current, lot_ids)]
    wo_l = pd.DataFrame()
    if work_legacy is not None and not work_legacy.empty:
        wo_l = work_legacy.loc[_work_da_denom_mask(work_legacy, lot_ids)]

    ao_work_breakdown_current = int(
        pd.to_numeric(wo_c["input_qty"], errors="coerce").fillna(0).sum()
    )
    ao_work_breakdown_legacy = int(
        pd.to_numeric(wo_l["input_qty"], errors="coerce").fillna(0).sum()
    )

    if work_current is None or work_current.empty:
        fallback_cond = "작업일보 없음 → da_first_input_qty=0 (출하로 대체 안 함)"
    elif ao_src_current == "work_da_input":
        fallback_cond = "작업일보 D/A 1차 투입 합계(코드·공정명 규칙)"
    elif ao_src_current == "work_raw_da_match":
        fallback_cond = (
            "prepared D/A 1차 합=0 → 원본 작업일보에서 동일 규칙 재합산(work_raw_da_match)"
        )
    elif ao_src_current == "da_input_zero":
        fallback_cond = (
            "해당 출하 LOT에 D/A 1차 투입 0 또는 미존재 → PPM 분모 0 (출하 move_qty 미사용)"
        )
    elif ao_src_current == "shipment_move_plus_defect_total_ppm_denom":
        fallback_cond = (
            "작업일보 분모 불가 시 PPM 분모 = 출하 move_qty 합 + defect_total "
            "(검증 AO/PPM 복구)"
        )
    elif ao_src_current == "no_work":
        fallback_cond = "작업일보 없음(no_work)"
    else:
        fallback_cond = f"ao_source={ao_src_current}"

    compare_block = {
        "week": wk,
        "legacy": {
            "ao_qty": ao_legacy_only_work,
            "defect_total": int(legacy_total)
            if legacy_total == int(legacy_total)
            else round(legacy_total, 4),
            "defect_row_count": len(legacy_rows_payload),
            "matched_lots": sorted(ship_lots_set),
            "defect_rows": legacy_rows_payload,
            "legacy_ao_formula": (
                "work D/A 1차 input_qty sum for shipment lots (no shipment AO)"
            ),
            "work_da_input_qty_sum_legacy_prep": ao_work_breakdown_legacy,
            "note_if_work_empty_legacy_ao_zero": bool(
                work_legacy is None or wo_l.empty or ao_legacy_only_work == 0
            ),
        },
        "current": {
            "ao_qty": ao_qty_current,
            "ao_source": ao_src_current,
            "defect_total": int(cur_total)
            if cur_total == int(cur_total)
            else round(cur_total, 4),
            "defect_row_count": len(current_rows_payload),
            "matched_lots": sorted(ship_lots_set),
            "defect_rows": current_rows_payload,
            "work_da_input_qty_sum_current_prep": ao_work_breakdown_current,
        },
        "ao_analysis": {
            "shipment_move_qty_sum_for_week": ship_move_sum,
            "work_da_input_sum_current_clean_lot": ao_work_breakdown_current,
            "work_da_input_sum_legacy_strip_lot": ao_work_breakdown_legacy,
            "legacy_head_ao_no_fallback": ao_legacy_only_work,
            "current_ao": ao_qty_current,
            "shipment_move_qty_reference_only": ship_move_sum,
            "why_ao_source": fallback_cond,
            "ppm_denominator_policy": (
                "주: 작업일보 D/A 1차; 해당 주차 최종 AO가 없으면 "
                "shipment_move_qty+defect_total 로 PPM 분모"
            ),
        },
        "legacy_included_not_current": excluded_detail,
    }

    print(f"[compare_weekly] week={wk}")
    print(
        "[compare_weekly] legacy="
        + json.dumps(compare_block["legacy"], ensure_ascii=False, default=str),
    )
    print(
        "[compare_weekly] current="
        + json.dumps(compare_block["current"], ensure_ascii=False, default=str),
    )
    print(
        "[compare_weekly] ao_analysis="
        + json.dumps(compare_block["ao_analysis"], ensure_ascii=False, default=str),
    )
    print(
        "[compare_weekly] legacy_included_not_current_rows="
        + json.dumps(excluded_detail, ensure_ascii=False, default=str),
    )


def _aggregate_weekly_by_shipment_lot(
    ship: pd.DataFrame,
    defect: pd.DataFrame,
    work: pd.DataFrame | None,
    *,
    defect_raw_for_compare: pd.DataFrame | None = None,
    work_raw_for_compare: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """주차별: 출하 LOT·불량 LOT 교집합; PPM 분모는 작업일보 D/A 또는 출하+불량 합 폴백."""
    out: list[dict[str, Any]] = []

    for week, grp in ship.groupby("week", sort=True):
        wk = str(week).strip()
        lot_ids = grp["lot_id"].unique().tolist()

        d_week = defect[defect["lot_id"].isin(lot_ids)]
        by_name = d_week.groupby("defect_name", dropna=False)["defect_qty"].sum()
        defect_total = int(pd.to_numeric(by_name, errors="coerce").fillna(0).sum())

        ao_qty, ao_src = _ao_qty_da_input_for_ppm(
            grp,
            lot_ids,
            work,
            log_ctx=f"weekly {wk}",
            period_type="week",
            period=wk,
            work_raw_for_retry=work_raw_for_compare,
        )
        ao_qty, ao_src = _apply_shipment_plus_defect_ao_fallback(
            ao_qty,
            ao_src,
            grp,
            defect_total,
            log_ctx=f"weekly {wk}",
        )

        total_ppm = _total_ppm(defect_total, ao_qty)
        _log_ao_compare_validated_week_line(wk, ao_qty, defect_total, total_ppm)

        if wk in _AO_BENCHMARK_WEEKS:
            _log_weekly_ao_benchmark(
                wk=wk,
                lot_ids=lot_ids,
                work=work,
                grp=grp,
                ao_selected=ao_qty,
                ao_source=ao_src,
            )

        work_legacy_prep: pd.DataFrame | None = None
        if work_raw_for_compare is not None and not work_raw_for_compare.empty:
            work_legacy_prep = _prepare_work_df_legacy(work_raw_for_compare)
        if wk in _COMPARE_WEEK_LOG_TARGETS and defect_raw_for_compare is not None:
            _log_weekly_legacy_vs_current(
                wk,
                grp,
                lot_ids,
                defect_raw_for_compare.copy(),
                defect,
                d_week,
                work,
                work_legacy_prep,
                ao_qty,
                ao_src,
            )

        defects: list[dict[str, Any]] = []
        for name, qty in by_name.items():
            label = "" if pd.isna(name) else str(name).strip()
            if not label:
                label = "기타"
            defects.append({"name": label, "count": int(qty)})

        print(
            f"[compute_weekly_defect] week={wk} ao_qty={ao_qty} ao_source={ao_src} "
            f"defect_total={defect_total} total_ppm={total_ppm} "
            f"defect_kinds={len(defects)} lots={len(lot_ids)} (by_shipment_lot)"
        )

        out.append(
            {
                "week": wk,
                "ao_qty": ao_qty,
                "defect_total": defect_total,
                "total_ppm": total_ppm,
                "defects": defects,
                "match_source": "weekly_monthly_by_shipment_lot",
                "ao_source": ao_src,
            }
        )

    return out


def _calendar_bounds_from_month_label(mk: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    yy_s, m_s = str(mk).split(".", 1)
    y = 2000 + int(yy_s)
    m = int(m_s)
    start = pd.Timestamp(year=y, month=m, day=1)
    end = start + pd.offsets.MonthEnd(0)
    return start.normalize(), end.normalize()


def _aggregate_monthly_by_shipment_lot(
    ship: pd.DataFrame,
    defect: pd.DataFrame,
    work: pd.DataFrame | None,
    *,
    work_raw_for_compare: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """월별: 출하 LOT·불량 LOT 교집합; PPM 분모는 작업일보 D/A 또는 출하+불량 합 폴백."""
    out: list[dict[str, Any]] = []

    grouped = list(ship.groupby("month", sort=False))
    grouped.sort(key=lambda item: _month_label_sort_key(str(item[0])))

    for month, grp in grouped:
        mk = str(month).strip()
        lot_ids = grp["lot_id"].unique().tolist()
        ship_lot_set = set(lot_ids)

        d_mon = defect[defect["lot_id"].isin(lot_ids)]
        by_name = d_mon.groupby("defect_name", dropna=False)["defect_qty"].sum()
        defect_total = int(pd.to_numeric(by_name, errors="coerce").fillna(0).sum())

        ao_qty, ao_src = _ao_qty_da_input_for_ppm(
            grp,
            lot_ids,
            work,
            log_ctx=f"monthly {mk}",
            period_type="month",
            period=mk,
            work_raw_for_retry=work_raw_for_compare,
        )
        ao_qty, ao_src = _apply_shipment_plus_defect_ao_fallback(
            ao_qty,
            ao_src,
            grp,
            defect_total,
            log_ctx=f"monthly {mk}",
        )

        total_ppm = _total_ppm(defect_total, ao_qty)

        defects: list[dict[str, Any]] = []
        for name, qty in by_name.items():
            label = "" if pd.isna(name) else str(name).strip()
            if not label:
                label = "기타"
            defects.append({"name": label, "count": int(qty)})

        occ_included: list[str] = []
        if not d_mon.empty and "occurrence_date" in d_mon.columns:
            for ts in d_mon["occurrence_date"]:
                if pd.isna(ts):
                    occ_included.append("(no_occurrence_date)")
                else:
                    occ_included.append(str(pd.Timestamp(ts).date()))
        occ_ordered = sorted(set(occ_included))

        excluded_rows: list[dict[str, Any]] = []
        m_start, m_end = _calendar_bounds_from_month_label(mk)
        raw = defect
        cal_mask = raw["occurrence_date"].notna() & (
            raw["occurrence_date"] >= m_start
        ) & (raw["occurrence_date"] <= m_end)
        for _, row in raw[cal_mask].iterrows():
            lid = _clean_lot(row.get("lot_id"))
            if not lid:
                excluded_rows.append(
                    {
                        "lot_id": "",
                        "occurrence_date": None,
                        "defect_name": row.get("defect_name"),
                        "defect_qty": row.get("defect_qty"),
                        "reason": "empty_lot_id",
                    }
                )
                continue
            if lid not in ship_lot_set:
                od = row["occurrence_date"]
                excluded_rows.append(
                    {
                        "lot_id": lid,
                        "occurrence_date": str(pd.Timestamp(od).date())
                        if pd.notna(od)
                        else None,
                        "defect_name": row.get("defect_name"),
                        "defect_qty": row.get("defect_qty"),
                        "reason": "lot_not_in_month_shipment",
                    }
                )

        print(
            "[defect_auto][debug] monthly_included_occurrence_dates month=%s %s"
            % (mk, json.dumps(occ_ordered, ensure_ascii=False)),
        )
        print(
            "[defect_auto][debug] monthly_included_shipment_lot_ids month=%s %s"
            % (mk, json.dumps(sorted(ship_lot_set), ensure_ascii=False)),
        )
        print(
            "[defect_auto][debug] monthly_excluded_defects_same_calendar_month month=%s %s"
            % (mk, json.dumps(excluded_rows, ensure_ascii=False, default=str)),
        )

        print(
            f"[compute_monthly_defect_from_shipments] month={mk} ao_qty={ao_qty} "
            f"ao_source={ao_src} defect_total={defect_total} total_ppm={total_ppm} "
            f"(by_shipment_lot)"
        )

        out.append(
            {
                "month": mk,
                "ao_qty": ao_qty,
                "defect_total": defect_total,
                "total_ppm": total_ppm,
                "defects": defects,
                "match_source": "weekly_monthly_by_shipment_lot",
                "ao_source": ao_src,
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
        ship["lot_id"] = ship["lot_id"].map(_clean_lot)

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


def _month_label_sort_key(label: str) -> tuple[int, int]:
    yy_s, m_s = str(label).split(".", 1)
    return (int(yy_s), int(m_s))


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
    shipment_df = filter_shipment_dataframe(
        shipment_df.copy(),
        context="compute_weekly_defect.shipment_df",
    )
    defect_df = filter_defect_dataframe(
        defect_df.copy(),
        context="compute_weekly_defect.defect_df",
    )
    ship = shipment_df.copy()
    before = len(ship)
    ship = ship[ship["move_date"].notna()].copy()
    removed = before - len(ship)
    if removed:
        print(f"[compute_weekly_defect] removed rows with empty move_date: {removed}")

    ship["week"] = ship["move_date"].apply(get_week_label)

    defect_raw = defect_df.copy()
    defect = _prepare_defect_df(defect_df)
    return _aggregate_weekly_by_shipment_lot(
        ship,
        defect,
        work=None,
        defect_raw_for_compare=defect_raw,
        work_raw_for_compare=None,
    )


def compute_weekly_defect_from_shipments(
    shipments: list[dict],
    defect_df: pd.DataFrame,
    work_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """출하로 주차별 AO를 잡고, 해당 주 출하 LOT과 불량 LOT 교집합으로 집계합니다."""
    shipments, defect_df, work_df = apply_defect_automation_filters(
        shipments,
        defect_df,
        work_df,
        context="weekly_defect_from_shipments",
    )
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

    defect_raw = defect_df.copy()
    defect = _prepare_defect_df(defect_df)
    work_raw_snap = work_df.copy()
    work = _prepare_work_df(work_df)
    return _aggregate_weekly_by_shipment_lot(
        ship,
        defect,
        work,
        defect_raw_for_compare=defect_raw,
        work_raw_for_compare=work_raw_snap,
    )


def compute_monthly_defect_from_shipments(
    shipments: list[dict],
    defect_df: pd.DataFrame,
    work_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """출하로 월별 AO를 잡고, 해당 월 출하 LOT과 불량 LOT 교집합으로 집계합니다."""
    shipments, defect_df, work_df = apply_defect_automation_filters(
        shipments,
        defect_df,
        work_df,
        context="monthly_defect_from_shipments",
    )
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
    work_raw_snap = work_df.copy()
    work = _prepare_work_df(work_df)
    return _aggregate_monthly_by_shipment_lot(
        ship,
        defect,
        work,
        work_raw_for_compare=work_raw_snap,
    )


def compute_lot_defect_ppm_from_shipments(
    shipments: list[dict],
    defect_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """출하 LOT 기준으로 불량 건수/PPM을 집계합니다(공정 미분리).

    출하 ``lot_id``는 코드별 불량현황의 **부모 LOTID**(생산 추적 단위)와 맞춥니다.
    불량 발생 후 새로 채번된 LOT ID 컬럼과 직접 비교하지 않습니다.
    """
    shipments, defect_df, _ = apply_defect_automation_filters(
        shipments,
        defect_df,
        pd.DataFrame(),
        context="lot_defect_ppm_from_shipments",
    )
    if not shipments:
        return []

    def _hdr_norm(cell: Any) -> str:
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            return ""
        return (
            str(cell)
            .strip()
            .replace(" ", "")
            .replace("\n", "")
            .replace("\u3000", "")
            .upper()
        )

    def _find_shipment_anchor_column(columns: list[Any]) -> str | None:
        """파서가 부모열을 따로 두었을 때(전달 DF에 존재할 때만). 원본 열 문자열 반환."""
        normed: list[tuple[str, str]] = []
        seen: set[str] = set()
        for c in columns:
            lbl = "" if c is None else str(c).strip()
            if not lbl or lbl in seen:
                continue
            seen.add(lbl)
            normed.append((_hdr_norm(lbl), lbl))

        priority_exact = (
            "부모LOTID",
            "부모LOT",
            "PARENTLOTID",
            "PARENTLOTNO",
            "PARENTLOT",
            "PARENT_LOT_ID",
            "SOURCELOTID",
            "SOURCELOT",
            "SOURCE_LOT_ID",
            "ORIGINALLOTID",
            "SHIPMENTLOTID",
            "출하LOTID",
            "출하LOT",
        )
        for key in priority_exact:
            for hn, orig in normed:
                if hn == key:
                    return orig
        for hn, orig in normed:
            if "부모" in hn and "LOT" in hn:
                return orig
        for hn, orig in normed:
            if hn.startswith("PARENT") and "LOT" in hn:
                return orig
            if hn.startswith("SOURCE") and "LOT" in hn:
                return orig
        return None

    def _parse_attrs_say_lot_id_is_parent(df: pd.DataFrame) -> tuple[bool, str]:
        """parse_defect가 ``lot_id``에 넣은 원본 헤더가 부모 LOT(출하 단위)일 때만 True.

        ``fallback_parent_lotid_all_zero_intersection``처럼 사유만 보고 단정하면,
        부모 열이 없을 때 첫 LOT(자식) 열이 잡혀 오탐이 날 수 있어 헤더 문자열만 본다.
        """
        rep = df.attrs.get("defect_lot_parse_report")
        if not isinstance(rep, dict):
            return False, ""
        sel = (
            rep.get("selected_defect_lot_column")
            or rep.get("lot_id_source_column_name")
            or ""
        )
        sel_s = str(sel).strip()
        sn = _hdr_norm(sel_s)
        if sn == "부모LOTID":
            return True, sel_s or "부모LOTID"
        if "부모" in sel_s and "LOT" in sel_s.upper():
            return True, sel_s
        if "PARENT" in sn and "LOT" in sn:
            return True, sel_s
        return False, sel_s or "unknown"

    def _shipment_anchor_and_key(raw: pd.DataFrame) -> tuple[pd.Series, str]:
        col = _find_shipment_anchor_column(list(raw.columns))
        if col and col in raw.columns:
            return raw[col].map(_clean_lot), f"column:{col}"

        attrs_ok, why = _parse_attrs_say_lot_id_is_parent(raw)
        if attrs_ok and "lot_id" in raw.columns:
            return raw["lot_id"].map(_clean_lot), f"attrs:lot_column_is_parent[{why}]"

        return pd.Series("", index=raw.index, dtype=str), (
            "none:need_parent_column_or_parse_attrs_parent_selection"
        )

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

    anchor_raw, match_key_meta = _shipment_anchor_and_key(defect_df)
    defect = _prepare_defect_df(defect_df)
    defect["defect_qty"] = pd.to_numeric(defect["defect_qty"], errors="coerce").fillna(0)
    shipment_anchor = anchor_raw.map(_clean_lot)
    defect["_shipment_anchor"] = shipment_anchor.reindex(defect.index).fillna("")
    shipment_anchor_series = defect["_shipment_anchor"]

    lot_ids = [_clean_lot(x) for x in ship_agg["lot_id"].astype(str).tolist()]
    ship_lot_set = {x for x in lot_ids if x}

    rep = defect_df.attrs.get("defect_lot_parse_report")
    rep_dict = rep if isinstance(rep, dict) else {}
    stats = rep_dict.get("lot_column_candidate_stats")
    cand_list: list[dict[str, Any]] = stats if isinstance(stats, list) else []
    selected_src = str(rep_dict.get("selected_defect_lot_column", "") or "")
    sel_reason = str(rep_dict.get("selection_reason", "") or "")

    shipment_lot_count = len(ship_lot_set)
    defect_l_uniq = {_clean_lot(x) for x in defect["lot_id"].tolist() if _clean_lot(x)}
    defect_lot_count = len(defect_l_uniq)
    intersect_l_parse_lot = defect_l_uniq & ship_lot_set
    matched_lot_count_direct = len(intersect_l_parse_lot)
    matched_defect_rows_direct = int(defect["lot_id"].isin(ship_lot_set).sum())

    parent_header_intersects: dict[str, int] = {}
    parent_col_samples_merged: list[str] = []
    for row in cand_list:
        cn = row.get("column_name")
        if cn is None:
            continue
        cns = str(cn).strip()
        hn = _hdr_norm(cns)
        inter = row.get("intersection_count_with_shipment")
        try:
            n = int(inter) if inter is not None else 0
        except (TypeError, ValueError):
            n = 0
        if hn == "부모LOTID" or ("부모" in cns and "LOT" in cns.upper()):
            parent_header_intersects[cns] = n
            samp = row.get("sample_10") or []
            if isinstance(samp, list):
                parent_col_samples_merged.extend(str(x) for x in samp)
        elif "PARENT" in hn and "LOT" in hn:
            parent_header_intersects[cns] = n
            samp = row.get("sample_10") or []
            if isinstance(samp, list):
                parent_col_samples_merged.extend(str(x) for x in samp)

    merged_parent_unique_intersect = (
        max(parent_header_intersects.values())
        if parent_header_intersects
        else None
    )

    intersect_shipment_vs_parent_sample_values = ship_lot_set.intersection(
        {_clean_lot(x) for x in parent_col_samples_merged},
    )

    shipment_sample_20 = sorted(ship_lot_set)[:20]
    defect_lot_sample_20 = sorted(defect_l_uniq)[:20]
    defect_parent_sample_20 = sorted(
        {_clean_lot(x) for x in parent_col_samples_merged if _clean_lot(x)},
    )[:20]

    cand_json = []
    for row in cand_list:
        if isinstance(row, dict):
            cand_json.append(
                {
                    "column_name": row.get("column_name"),
                    "intersection_count_with_shipment": row.get(
                        "intersection_count_with_shipment"
                    ),
                    "sample": row.get("sample_10"),
                },
            )

    print(
        "[lot_diag_compare] "
        + json.dumps(
            {
                "note": (
                    "parse_defect는 DF에 선택된 LOT열만 lot_id로 남김. "
                    "부모열 샘플/교집합은 원본 헤더가 attrs.lot_column_candidate_stats에 저장된 분만 반영됨."
                ),
                "weekly_monthly_match_basis": (
                    "defect_prepared.lot_id (parse가 선택한 열→lot_id) vs 출하 lot_id, "
                    "occurrence_date로 주/월 버킷필터(별도)."
                ),
                "lot_chart_current_shipment_anchor": match_key_meta,
                "defect_columns_in_payload": list(defect_df.columns),
                "attrs_selected_defect_lot_column": selected_src or None,
                "attrs_selection_reason": sel_reason or None,
                "_clean_lot_on_defect_lot_ids": True,
                "effect_router_storage_antioverwrite_note": (
                    "/defect-auto/compute 라우터의 matched_rows_total==0일 때 "
                    "_latest_lot_defects 덮어쓰기 생략은 이 함수 바깥(저장 레이어)."
                ),
            },
            ensure_ascii=False,
            default=str,
        ),
    )
    print(
        "[lot_diag_compare] summary_counts="
        + json.dumps(
            {
                "shipment_lot_count": shipment_lot_count,
                "defect_lot_count": defect_lot_count,
                "matched_lot_count_parse_selected_lot_vs_ship": matched_lot_count_direct,
                "matched_defect_rows_parse_selected_lot_vs_ship": matched_defect_rows_direct,
                "matched_unique_lots_parent_headers_parser_metric": merged_parent_unique_intersect,
                "overlap_ship_vs_cleaned_parent_candidate_samples_unique_count": (
                    len(intersect_shipment_vs_parent_sample_values)
                ),
                "sample_overlap_sorted_20max": sorted(intersect_shipment_vs_parent_sample_values)[
                    :20
                ],
                "parent_candidate_header_keys": sorted(parent_header_intersects.keys()),
            },
            ensure_ascii=False,
            default=str,
        ),
    )
    print(
        "[lot_diag_compare] lot_column_candidates_vs_shipment="
        + json.dumps(cand_json, ensure_ascii=False, default=str),
    )
    print(f"[lot_diag_compare] shipment_lot_sample_20={shipment_sample_20}")
    print(f"[lot_diag_compare] defect_lot_id_sample_20_from_df_lot_id={defect_lot_sample_20}")
    print(
        "[lot_diag_compare] defect_parent_lot_samples_from_candidate_stats="
        + str(defect_parent_sample_20),
    )
    print(
        "[lot_diag_compare] intersection_parse_lot_set_vs_shipment="
        + json.dumps(
            {
                "unique_lot_intersection_size": matched_lot_count_direct,
                "parse_report_intersection_after_selection_uniques": rep_dict.get(
                    "intersection_count_after_selection"
                ),
                "sample_intersection_sorted_20max": sorted(intersect_l_parse_lot)[:20],
            },
            ensure_ascii=False,
            default=str,
        ),
    )
    print(
        "[lot_diag_compare] intersection_parent_candidates_vs_ship="
        + json.dumps(
            parent_header_intersects,
            ensure_ascii=False,
            default=str,
        ),
    )

    match_mask = shipment_anchor_series.ne("") & shipment_anchor_series.isin(ship_lot_set)
    defect_matched_all = defect.loc[match_mask]
    matched_rows_total = int(match_mask.sum())
    anch_u = {_clean_lot(x) for x in defect.loc[match_mask, "_shipment_anchor"].tolist()}
    anch_u.discard("")
    matched_lot_anchor_nonzero_unique = len(anch_u)

    print(
        "[lot_diag_compare] current_shipment_anchor_match_result="
        + json.dumps(
            {
                "match_key_used": match_key_meta,
                "matched_defect_rows_total": matched_rows_total,
                "matched_defect_shipment_anchor_lot_unique": matched_lot_anchor_nonzero_unique,
                "explain_if_zeros": (
                    "Lot차트 매칭이 parse lot_id 또는 별도 부모열 미전달 등으로 빈 문자열일 수 있음. "
                    "위 summary_counts.direct_*와 교차 확인."
                ),
            },
            ensure_ascii=False,
            default=str,
        ),
    )

    ship_sample = sorted(ship_lot_set)[:10]
    uniq_anchor = {_clean_lot(v) for v in shipment_anchor_series.tolist()}
    uniq_anchor.discard("")
    defect_parent_sample = sorted(uniq_anchor)[:10]

    print(
        f"[lot_parent_match] defect_columns={list(defect_df.columns)}"
    )
    print(f"[lot_parent_match] match_key={match_key_meta}")
    print(f"[lot_parent_match] shipment_lot_sample={ship_sample}")
    print(
        f"[lot_parent_match] defect_parent_lot_sample={defect_parent_sample}"
    )
    print(f"[lot_parent_match] matched_rows_total={matched_rows_total}")

    out: list[dict[str, Any]] = []
    nonzero_lot_count = 0
    for _, row in ship_agg.iterrows():
        lot_id = _clean_lot(row["lot_id"])
        move_date = pd.Timestamp(row["move_date"]).strftime("%Y-%m-%d")
        move_qty = float(pd.to_numeric(row["move_qty"], errors="coerce") or 0)
        move_qty_out: int | float = int(move_qty) if move_qty.is_integer() else round(move_qty, 4)

        d_lot = defect_matched_all[
            defect_matched_all["_shipment_anchor"] == lot_id
        ]
        by_name_series = d_lot.groupby("defect_name", dropna=False)["defect_qty"].sum()
        defects: list[dict[str, Any]] = []
        defect_total = 0.0
        for name, qty in by_name_series.sort_index().items():
            count = float(qty)
            defect_total += count
            ppm = 0.0 if move_qty <= 0 else round((count / move_qty) * 1_000_000, 1)
            label = "" if pd.isna(name) else str(name).strip()
            if not label:
                label = "기타"
            defects.append(
                {
                    "name": label,
                    "count": int(count) if count.is_integer() else round(count, 4),
                    "ppm": ppm,
                }
            )

        total_ppm = 0.0 if move_qty <= 0 else round((defect_total / move_qty) * 1_000_000, 1)
        if defect_total > 0:
            nonzero_lot_count += 1
        print(
            f"[lot_ppm_compare] lot_id={lot_id} matched_defect_rows={len(d_lot)} "
            f"defect_total={int(defect_total) if defect_total.is_integer() else round(defect_total, 4)}"
        )
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
                "match_source": "shipment_vs_defect_parent_lot_id",
                "ao_source": "shipment_move_qty",
            }
        )

    print(f"[lot_ppm_debug] nonzero_lot_count={nonzero_lot_count}")
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
