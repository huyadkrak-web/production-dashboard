from __future__ import annotations

import logging
import re
from datetime import date, datetime
from io import BytesIO
from typing import Any, Iterable

import pandas as pd

from .settings import settings

_log = logging.getLogger(__name__)

# 작업일보 시트 상단 메타/제목 행 스캔 시 최대 행 수
_WORK_HEADER_SCAN_ROWS = 80


def _work_sheet_anchor_columns() -> frozenset[str]:
    """한 행에 모두 있으면 작업일보 헤더로 간주하는 앵커 컬럼명."""
    return frozenset(
        {
            settings.work_col_process_code,
            settings.work_col_process_name,
            settings.work_col_date,
            settings.work_col_good_qty,
            settings.work_col_defect_qty,
        }
    )


def _detect_work_sheet_header_row(xls: pd.ExcelFile, sheet: str) -> int | None:
    """header=None으로 읽은 상단 구간에서 앵커 컬럼이 한 줄에 모두 있는 행 인덱스(0-based)."""
    raw = pd.read_excel(
        xls,
        sheet_name=sheet,
        header=None,
        nrows=_WORK_HEADER_SCAN_ROWS,
    )
    if raw is None or raw.empty:
        return None
    anchors = _work_sheet_anchor_columns()
    for i in range(len(raw)):
        cells: set[str] = set()
        for v in raw.iloc[i]:
            if pd.isna(v):
                continue
            s = str(v).strip()
            if s and s.lower() != "nan":
                cells.add(s)
        if anchors.issubset(cells):
            return i
    return None


def _read_work_sheet_dataframe(
    xls: pd.ExcelFile, sheet: str, warnings: list[str]
) -> pd.DataFrame:
    """작업일보/전일작업일보: 헤더 행 자동 탐지 후 DataFrame 로드."""
    hr = _detect_work_sheet_header_row(xls, sheet)
    if hr is not None:
        df = pd.read_excel(xls, sheet_name=sheet, header=hr)
        df.attrs["work_sheet_header_row_1based"] = hr + 1
    else:
        df = pd.read_excel(xls, sheet_name=sheet, header=0)
        df.attrs["work_sheet_header_row_1based"] = None
        warnings.append(
            f"시트 '{sheet}': 앵커 컬럼으로 헤더 행을 찾지 못해 1행을 헤더로 사용합니다."
        )
    return df


def _resolve_work_product_source_column(df: pd.DataFrame, warnings: list[str]) -> str:
    """
    settings.work_col_product(제품군)에 집계용 product 값을 채운 뒤,
    로그용으로 '값의 출처가 된 원본 컬럼명'을 반환한다.
    """
    tgt = settings.work_col_product

    def _col_nonempty(name: str) -> bool:
        if name not in df.columns:
            return False
        s = df[name].map(lambda x: "" if pd.isna(x) else str(x).strip())
        return bool(((s != "") & (s.str.upper() != "NAN")).any())

    if _col_nonempty(tgt):
        return tgt

    for alt in ("품목명", "품목ID"):
        if not _col_nonempty(alt):
            continue
        if tgt not in df.columns:
            df[tgt] = df[alt]
        else:
            st = df[tgt].map(lambda x: "" if pd.isna(x) else str(x).strip())
            mask = (st == "") | (st.str.upper() == "NAN")
            df.loc[mask, tgt] = df.loc[mask, alt]
        warnings.append(
            f"작업일보: '{tgt}'가 비어 있거나 없어 product 값에 '{alt}'를 사용(보완)했습니다."
        )
        return alt

    return tgt if tgt in df.columns else f"(없음:{tgt})"


def _safe_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        if isinstance(x, str) and not x.strip():
            return 0.0
        v = float(x)
        if pd.isna(v):
            return 0.0
        return v
    except Exception:
        return 0.0


# YYYY-MM-DD / YYYY/MM/DD(월·일 1~2자리) — dayfirst 적용 시 월/일이 뒤바뀌므로 year-first로만 파싱
_YEAR_FIRST_DATE_STR = re.compile(r"^\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}")


def _to_date_series(s: pd.Series) -> pd.Series:
    """엑셀 날짜(숫자) + 문자열 날짜를 최대한 안전하게 date로 변환."""
    # 숫자형 엑셀 일련번호 처리 (1900 기준, 윤년 버그는 무시)
    def _convert_cell(v: Any) -> Any:
        if isinstance(v, (int, float)) and not pd.isna(v):
            try:
                # Excel serial date (days since 1899-12-30)
                return pd.Timestamp("1899-12-30") + pd.to_timedelta(int(v), unit="D")
            except Exception:
                return v
        return v

    def _to_timestamp(v: Any) -> pd.Timestamp:
        if v is None:
            return pd.NaT
        if isinstance(v, (float, int)) and pd.isna(v):
            return pd.NaT
        if isinstance(v, pd.Timestamp):
            return v.normalize()
        if isinstance(v, datetime):
            return pd.Timestamp(v)
        if type(v) is date:
            return pd.Timestamp(v)
        if isinstance(v, str):
            t = v.strip()
            if not t or t.lower() == "nan":
                return pd.NaT
            if _YEAR_FIRST_DATE_STR.match(t):
                return pd.to_datetime(t, errors="coerce", dayfirst=False)
            return pd.to_datetime(t, errors="coerce", dayfirst=True)
        return pd.to_datetime(v, errors="coerce", dayfirst=False)

    s_converted = s.map(_convert_cell)
    ts = s_converted.map(_to_timestamp)
    return ts.dt.date


def read_excel_any_sheets(file_bytes: bytes) -> tuple[dict[str, pd.DataFrame], list[str]]:
    warnings: list[str] = []
    dfs: dict[str, pd.DataFrame] = {}
    bio = BytesIO(file_bytes)
    try:
        xls = pd.ExcelFile(bio, engine="openpyxl")
    except Exception as e:
        raise ValueError(f"엑셀 파일을 읽을 수 없습니다: {e}") from e

    for sheet in xls.sheet_names:
        try:
            if sheet in (settings.sheet_work_today, settings.sheet_work_prev):
                df = _read_work_sheet_dataframe(xls, sheet, warnings)
            else:
                df = pd.read_excel(xls, sheet_name=sheet)
            if df is None or df.empty:
                continue
            df.columns = [str(c).strip() for c in df.columns]
            dfs[sheet] = df
        except Exception as e:
            warnings.append(f"시트 '{sheet}'를 읽지 못했습니다: {e}")
    if not dfs:
        raise ValueError("엑셀에서 읽을 수 있는 데이터 시트가 없습니다.")
    return dfs, warnings


def _ensure_columns(df: pd.DataFrame, cols: Iterable[str], warnings: list[str]) -> None:
    for c in cols:
        if c not in df.columns:
            df[c] = None
            warnings.append(f"컬럼 '{c}'가 없어 0/빈값으로 처리합니다.")


# 작업일보 Excel 컬럼명 -> 내부 표준 컬럼명 (compute 내부는 이 이름만 사용)
def _work_rename() -> dict[str, str]:
    return {
        settings.work_col_date: "work_date",
        settings.work_col_product: "product",
        settings.work_col_process_code: "process_code",
        settings.work_col_process_name: "process_name",
        settings.work_col_good_qty: "good_qty",
        settings.work_col_defect_qty: "defect_qty",
        settings.work_col_defect_type: "defect_type",
    }


def _ppm(defect: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return (defect / total) * 1_000_000.0


def _ensure_unique_for_reindex(
    s: pd.Series,
    name: str,
    warnings: list[str],
    agg: str | callable = "sum",
) -> pd.Series:
    """reindex 전에 MultiIndex가 unique가 되도록 보정."""
    if s.index.is_unique:
        return s
    # level 0..n-1 기준 groupby 집계
    levels = list(range(s.index.nlevels))
    grouped = s.groupby(level=levels).agg(agg)
    warnings.append(f"'{name}' Series의 인덱스가 중복되어 {agg!r} 기준으로 집계 후 사용했습니다.")
    return grouped


def _load_work(df_work: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    """작업일보 / 전일작업일보 시트 공통 전처리."""
    header_row_1based = df_work.attrs.get("work_sheet_header_row_1based")
    df = df_work.copy()
    df.columns = [str(c).strip() for c in df.columns]

    product_source_col = _resolve_work_product_source_column(df, warnings)

    needed = [
        settings.work_col_date,
        settings.work_col_product,
        settings.work_col_process_code,
        settings.work_col_process_name,
        settings.work_col_good_qty,
        settings.work_col_defect_qty,
        settings.work_col_defect_type,
    ]
    _ensure_columns(df, needed, warnings)

    df[settings.work_col_product] = df[settings.work_col_product].astype(str).fillna("").str.strip()
    df[settings.work_col_process_code] = (
        df[settings.work_col_process_code].astype(str).fillna("").str.strip()
    )
    df[settings.work_col_process_name] = (
        df[settings.work_col_process_name].astype(str).fillna("").str.strip()
    )
    df[settings.work_col_date] = _to_date_series(df[settings.work_col_date])

    for c in [settings.work_col_good_qty, settings.work_col_defect_qty]:
        df[c] = df[c].map(_safe_float)

    df[settings.work_col_defect_type] = (
        df[settings.work_col_defect_type].astype(str).fillna("").str.strip()
    )
    columns_before_internal_rename = list(df.columns)
    # Excel 컬럼명 -> 내부 표준 컬럼명으로 rename (이후 compute는 내부명만 사용)
    rename_map = {k: v for k, v in _work_rename().items() if k in df.columns}
    df = df.rename(columns=rename_map)

    _log.info("[작업일보] 최종 인식된 컬럼명 목록=%s", columns_before_internal_rename)
    _log.info("[작업일보] 선택된 헤더 행 번호(엑셀 1-based)=%s", header_row_1based)
    _log.info(
        "[작업일보] product 매핑 원본 컬럼명=%s (내부 rename 전 키=%s)",
        product_source_col,
        settings.work_col_product,
    )
    if "product" in df.columns:
        _log.info(
            "[작업일보] product 샘플(10)=%s",
            df["product"].astype(str).head(10).tolist(),
        )
    if "process_code" in df.columns:
        _log.info(
            "[작업일보] process_code 샘플(10)=%s",
            df["process_code"].astype(str).head(10).tolist(),
        )
    if "process_name" in df.columns:
        _log.info(
            "[작업일보] process_name 샘플(10)=%s",
            df["process_name"].astype(str).head(10).tolist(),
        )

    return df


def _master_from_api(master_list: list[dict[str, Any]], warnings: list[str]) -> pd.DataFrame:
    """저장소에서 로드한 기준정보 리스트 -> 내부 표준 컬럼 DataFrame. is_active 필터."""
    if not master_list:
        raise ValueError("기준정보가 비어 있습니다.")
    df = pd.DataFrame(master_list)
    for col in ["product", "process_code", "process_name", "process_group", "is_assembly", "display_order", "is_active"]:
        if col not in df.columns:
            if col == "is_active":
                df[col] = True
            elif col == "display_order":
                df[col] = 0.0
            elif col == "is_assembly":
                df[col] = "N"
            else:
                df[col] = ""
    df["product"] = df["product"].astype(str).fillna("").str.strip()
    df["process_code"] = df["process_code"].astype(str).fillna("").str.strip()
    df["process_name"] = df["process_name"].astype(str).fillna("").str.strip()
    df["process_group"] = df["process_group"].astype(str).fillna("").str.strip()
    df["is_assembly"] = df["is_assembly"].astype(str).fillna("N").str.strip().str.upper()
    df["display_order"] = df["display_order"].map(_safe_float)
    # is_active 비활성 행 제외
    if "is_active" in df.columns:
        active = df["is_active"]
        if active.dtype == bool:
            df = df.loc[active].copy()
        else:
            df = df.loc[active.astype(str).str.upper().isin(("Y", "YES", "1", "TRUE"))].copy()
    if df.empty:
        raise ValueError("기준정보에 활성 행이 없습니다.")
    key_cols = ["product", "process_code"]
    n_before = len(df)
    df = df.groupby(key_cols, dropna=False).agg(
        process_name=("process_name", "first"),
        process_group=("process_group", "first"),
        is_assembly=("is_assembly", "first"),
        display_order=("display_order", "min"),
    ).reset_index()
    if len(df) < n_before:
        warnings.append("기준정보에서 product+process_code 중복이 있어 첫 행 기준으로 병합했습니다.")
    return df


def _plan_from_api(plan_list: list[dict[str, Any]], warnings: list[str]) -> tuple[pd.DataFrame, float, str]:
    """저장소에서 로드한 월간플랜 리스트 -> 내부 표준 컬럼 DataFrame, month_total, month_label."""
    if not plan_list:
        raise ValueError("월간플랜이 비어 있습니다.")
    df = pd.DataFrame(plan_list)
    for col in ["product", "process_code", "month_plan", "prev_day_plan"]:
        if col not in df.columns:
            df[col] = 0.0 if col in ("month_plan", "prev_day_plan") else ""
    df["product"] = df["product"].astype(str).fillna("").str.strip()
    df["process_code"] = df["process_code"].astype(str).fillna("").str.strip()
    df["month_plan"] = df["month_plan"].map(_safe_float)
    df["prev_day_plan"] = df["prev_day_plan"].map(_safe_float)
    key_cols = ["product", "process_code"]
    df_agg = df.groupby(key_cols, dropna=False).agg(
        month_plan=("month_plan", "max"),
        prev_day_plan=("prev_day_plan", "max"),
    ).reset_index()
    month_total = float(df_agg["month_plan"].sum())
    month_str = str(plan_list[0].get("month", "")).strip() if plan_list else ""
    if month_str and len(month_str) >= 7:
        try:
            _y, _m = month_str.split("-")[:2]
            month_label = f"{int(_m)}월"
        except Exception:
            month_label = month_str
    else:
        month_label = month_str or "월"
    return df_agg, month_total, month_label


def compute_tables(
    master_list: list[dict[str, Any]],
    plan_list: list[dict[str, Any]],
    today_file_bytes: bytes,
    base_date: date,
    defect_list: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # 실사용 기준: 사용자가 선택한 base_date 자체를 "전일" 집계 기준으로 사용
    # (meta.prev_date 필드도 동일 값으로 반환)
    prev_date = base_date
    warnings: list[str] = []

    df_master = _master_from_api(master_list, warnings)
    df_plan, month_total, month_label = _plan_from_api(plan_list, warnings)

    # defect_list: 참고용 문자열만 defect_cumulative_types에 반영 (전일/누적 개수·PPM은 Excel Reject 전용)
    # 새 구조: 제품 + 공정대분류(Front/Back End) 단위로 multi-line 텍스트를 저장
    defect_manual_latest: dict[tuple[str, str], tuple[str, str]] = {}
    if defect_list:
        for d in defect_list:
            d_date = str(d.get("date") or "").strip()
            if not d_date or d_date > str(base_date):
                continue
            product = str(d.get("product", "")).strip()
            process_group = str(d.get("process_group", "")).strip()
            summary = str(d.get("defect_summary", "")).strip()
            if not product or not process_group or not summary:
                continue
            key = (product, process_group)
            prev = defect_manual_latest.get(key)
            if prev is None or prev[0] <= d_date:
                defect_manual_latest[key] = (d_date, summary)

    defect_manual_joined = {k: v[1] for k, v in defect_manual_latest.items()}

    today_sheets, w1 = read_excel_any_sheets(today_file_bytes)
    warnings.extend(w1)

    def _get_sheet(d: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
        if name not in d:
            raise ValueError(f"시트 '{name}'를 찾을 수 없습니다.")
        return d[name]

    df_work_today_raw = _get_sheet(today_sheets, settings.sheet_work_today)
    _PREV_DAY_ISSUE_BASE = date(2026, 3, 9)
    _issue_raw_date_sample: list[Any] = []
    if base_date == _PREV_DAY_ISSUE_BASE:
        _wcol = settings.work_col_date
        if _wcol in df_work_today_raw.columns:
            _issue_raw_date_sample = df_work_today_raw[_wcol].head(10).tolist()
        else:
            _issue_raw_date_sample = [f"<missing column {_wcol!r}>"]

    df_work_today = _load_work(df_work_today_raw, warnings)

    # 내부 표준 컬럼명 사용 (work_date, product, process_code, good_qty, defect_qty, defect_type)
    key_cols = ["product", "process_code"]
    work_date_col = "work_date"
    good_qty_col = "good_qty"
    defect_qty_col = "defect_qty"
    defect_type_col = "defect_type"

    # work_date는 _to_date_series()로 datetime.date(또는 NaT/NaN) — base_date와 동일 타입으로 비교
    _wd_series = df_work_today[work_date_col]
    _wd_sample_10 = _wd_series.dropna().head(10).tolist()
    _log.info(
        "[날짜비교] base_date 타입=%s 값=%s",
        type(base_date).__name__,
        base_date,
    )
    _log.info(
        "[날짜비교] work_date dtype=%s 비교 직전 샘플(10)=%s",
        _wd_series.dtype,
        _wd_sample_10,
    )

    # 날짜 필터 (누적: 작업일보에서 base_date까지)
    df_today_upto = df_work_today[
        (df_work_today[work_date_col].notna())
        & (df_work_today[work_date_col] <= base_date)
    ]
    if df_work_today[work_date_col].notna().any():
        df_prev_day = df_work_today[df_work_today[work_date_col] == base_date]
        if df_prev_day.empty:
            warnings.append(
                "작업일보에서 전일(=기준일) 데이터가 비어있습니다. 전일 값이 0으로 나올 수 있습니다."
            )
    else:
        warnings.append("작업일보에 작업종료일자 파싱 실패로, 전체를 전일 데이터로 간주합니다.")
        df_prev_day = df_work_today

    # 누적 실적(양품)
    g_upto = df_today_upto.groupby(key_cols, dropna=False)
    good_cum = g_upto[good_qty_col].sum().fillna(0.0)

    # 전일 실적(양품) - 작업일보에서 base_date(=전일 기준일) 행만 집계
    g_prev = df_prev_day.groupby(key_cols, dropna=False)
    good_prev = g_prev[good_qty_col].sum().fillna(0.0)

    # 조립 공정 누적/전일 실적 및 불량
    g_upto_asm = df_today_upto.groupby(key_cols, dropna=False)
    asm_good_cum = g_upto_asm[good_qty_col].sum().fillna(0.0)
    asm_def_cum = g_upto_asm[defect_qty_col].sum().fillna(0.0)

    g_prev_asm = df_prev_day.groupby(key_cols, dropna=False)
    asm_good_prev = g_prev_asm[good_qty_col].sum().fillna(0.0)
    asm_def_prev = g_prev_asm[defect_qty_col].sum().fillna(0.0)

    if base_date == _PREV_DAY_ISSUE_BASE:

        def _emit_issue(msg: str) -> None:
            _log.info(msg)
            print(msg)

        _wn = df_work_today[work_date_col].dropna()
        _wmin = _wn.min() if not _wn.empty else None
        _wmax = _wn.max() if not _wn.empty else None
        _conv10 = df_work_today[work_date_col].head(10).tolist()
        _prev_filter_n = len(df_prev_day)
        _cols_prev = [c for c in ("product", "process_code", "process_name", good_qty_col) if c in df_prev_day.columns]
        if not df_prev_day.empty and _cols_prev:
            _samp20 = df_prev_day[_cols_prev].head(20).to_dict(orient="records")
        else:
            _samp20 = []
        _gp_dict = good_prev.to_dict()
        if len(_gp_dict) > 50:
            _gp_issue_show = dict(list(_gp_dict.items())[:50])
            _gp_note = f" (상위 {len(_gp_issue_show)}개만, 전체 {len(_gp_dict)}키)"
        else:
            _gp_issue_show = _gp_dict
            _gp_note = f" (전체 {len(_gp_dict)}키)"

        _emit_issue(f"[PREV_DAY_ISSUE] base_date={base_date}")
        _emit_issue(f"[PREV_DAY_ISSUE] df_work_today 전체 row 수={len(df_work_today)}")
        _emit_issue(f"[PREV_DAY_ISSUE] work_date 원본(작업종료일자) 샘플10={_issue_raw_date_sample}")
        _emit_issue(f"[PREV_DAY_ISSUE] work_date 변환 후 샘플10={_conv10}")
        _emit_issue(f"[PREV_DAY_ISSUE] work_date min={_wmin} max={_wmax}")
        _emit_issue(f"[PREV_DAY_ISSUE] work_date == base_date 필터 후 row 수={_prev_filter_n}")
        _emit_issue(f"[PREV_DAY_ISSUE] 필터 후 product/process_code/process_name/good_qty 샘플20={_samp20}")
        _emit_issue(f"[PREV_DAY_ISSUE] good_prev groupby 결과{_gp_note}={_gp_issue_show}")

    work_date_non_null = df_work_today[work_date_col].dropna()
    work_date_sample_10 = work_date_non_null.head(10).tolist()
    work_date_min = work_date_non_null.min() if not work_date_non_null.empty else None
    work_date_max = work_date_non_null.max() if not work_date_non_null.empty else None
    good_prev_sample = good_prev.head(10).to_dict()
    asm_good_prev_sample = asm_good_prev.head(10).to_dict()

    prev_day_debug_lines = [
        f"[PREV_DAY_DEBUG] base_date={base_date}",
        f"[PREV_DAY_DEBUG] df_work_today rows={len(df_work_today)}",
        f"[PREV_DAY_DEBUG] work_date sample10={work_date_sample_10}",
        f"[PREV_DAY_DEBUG] work_date min={work_date_min} max={work_date_max}",
        f"[PREV_DAY_DEBUG] cumulative filtered rows={len(df_today_upto)}",
        f"[PREV_DAY_DEBUG] prev_day(base_date) filtered rows={len(df_prev_day)}",
        f"[PREV_DAY_DEBUG] good_prev sample={good_prev_sample}",
        f"[PREV_DAY_DEBUG] asm_good_prev sample={asm_good_prev_sample}",
        f"[PREV_DAY_DEBUG] production_progress_target_rows={len(good_prev)}",
        f"[PREV_DAY_DEBUG] assembly_prev_day_target_rows={len(asm_good_prev)}",
    ]
    for line in prev_day_debug_lines:
        _log.info(line)
        print(line)

    # 누적 불량유형
    if defect_type_col in df_today_upto.columns:
        df_def = df_today_upto[
            (df_today_upto[defect_type_col] != "")
            & (df_today_upto[defect_qty_col] > 0)
        ][key_cols + [defect_type_col, defect_qty_col]].copy()

        if df_def.empty:
            def_types = pd.Series(dtype=str)
        else:
            by_type = (
                df_def.groupby(key_cols + [defect_type_col], dropna=False)[defect_qty_col]
                .sum()
                .reset_index()
            )

            def _fmt_group(g: pd.DataFrame) -> str:
                g2 = g.sort_values(
                    by=[defect_qty_col, defect_type_col],
                    ascending=[False, True],
                )
                lines = [
                    f"{str(row[defect_type_col]).strip()} : {int(_safe_float(row[defect_qty_col]))}"
                    for _, row in g2.iterrows()
                    if str(row[defect_type_col]).strip()
                ]
                return "\n".join(lines)

            def_types = by_type.groupby(key_cols, dropna=False).apply(_fmt_group)
    else:
        def_types = pd.Series(dtype=str)
        warnings.append("작업일보에 불량유형 컬럼이 없어 누적불량유형이 비게 됩니다.")

    # Plan 조인 (내부키 product + process_code)
    plan_key = ["product", "process_code"]
    df_plan_keyed = df_plan.set_index(plan_key)

    # 기준(공정 테이블) 기반으로 최종 행 구성 (내부키 product + process_code)
    master_key = ["product", "process_code"]
    df_master_keyed = df_master.set_index(master_key)
    if not df_master_keyed.index.is_unique:
        df_master_keyed = (
            df_master_keyed.groupby(level=list(range(df_master_keyed.index.nlevels))).first()
        )
        warnings.append("기준 데이터 인덱스가 중복되어 first 기준으로 병합했습니다.")

    idx_all = df_master_keyed.index

    # Plan 값 (내부 표준 컬럼명 month_plan, prev_day_plan)
    month_plan_raw = df_plan_keyed.get("month_plan", pd.Series(0.0, index=idx_all))
    prev_plan_raw = df_plan_keyed.get("prev_day_plan", pd.Series(0.0, index=idx_all))
    month_plan_raw = _ensure_unique_for_reindex(month_plan_raw, "month_plan", warnings, agg="max")
    prev_plan_raw = _ensure_unique_for_reindex(prev_plan_raw, "prev_day_plan", warnings, agg="max")
    month_plan = month_plan_raw.reindex(idx_all, fill_value=0.0)
    prev_plan = prev_plan_raw.reindex(idx_all, fill_value=0.0)

    # 실적/불량 계열을 기준 인덱스로 재배열 (unique 보장 후 reindex)
    good_cum = _ensure_unique_for_reindex(good_cum, "good_cum", warnings, agg="sum").reindex(
        idx_all, fill_value=0.0
    )
    good_prev = _ensure_unique_for_reindex(good_prev, "good_prev", warnings, agg="sum").reindex(
        idx_all, fill_value=0.0
    )

    asm_good_cum = _ensure_unique_for_reindex(
        asm_good_cum, "asm_good_cum", warnings, agg="sum"
    ).reindex(idx_all, fill_value=0.0)
    asm_good_prev = _ensure_unique_for_reindex(
        asm_good_prev, "asm_good_prev", warnings, agg="sum"
    ).reindex(idx_all, fill_value=0.0)
    asm_def_cum = _ensure_unique_for_reindex(
        asm_def_cum, "asm_def_cum", warnings, agg="sum"
    ).reindex(idx_all, fill_value=0.0)
    asm_def_prev = _ensure_unique_for_reindex(
        asm_def_prev, "asm_def_prev", warnings, agg="sum"
    ).reindex(idx_all, fill_value=0.0)

    def_types = _ensure_unique_for_reindex(
        def_types, "defect_types", warnings, agg=lambda s: "\n".join(sorted(set(map(str, s))))
    ).reindex(idx_all, fill_value="")

    # 공정명/대분류/조립공정 플래그/표시순서 (내부 표준 컬럼명)
    proc_name = df_master_keyed["process_name"]
    proc_group = df_master_keyed["process_group"]
    is_assembly_flag = df_master_keyed.get("is_assembly", pd.Series("N", index=idx_all))
    display_order = df_master_keyed.get("display_order", pd.Series(0.0, index=idx_all)).map(_safe_float)

    def _to_scalar_display(v: Any) -> float:
        if isinstance(v, pd.Series):
            if v.empty:
                return 9999.0
            v = v.min()
        f = _safe_float(v)
        if pd.isna(f):
            return 9999.0
        return f

    def _sort_key_idx(idx: Any) -> tuple[float, str, str]:
        """정렬: display_order 만 사용 (product 고정 없음)."""
        prod, code = idx
        name = str(proc_name.loc[idx]) if idx in proc_name.index else ""
        group = str(proc_group.loc[idx]) if idx in proc_group.index else ""
        disp_order = _to_scalar_display(display_order.loc[idx] if idx in display_order.index else 9999.0)
        return (disp_order, group, name)

    sorted_idx = sorted(list(idx_all), key=_sort_key_idx)

    if base_date == _PREV_DAY_ISSUE_BASE:

        def _emit_issue2(msg: str) -> None:
            _log.info(msg)
            print(msg)

        _target_codes = ("FDA01", "FWB01", "BMD01", "BPS01", "BLM01", "FCD01")
        for _idx in sorted_idx:
            if _idx[1] not in _target_codes:
                continue
            _gp = float(good_prev.loc[_idx])
            _emit_issue2(
                f"[PREV_DAY_ISSUE] prev_day_actual 반영 직전(재색인 후 good_prev) "
                f"product={_idx[0]!r} process_code={_idx[1]!r} gp={_gp}",
            )
        for _idx in sorted_idx:
            if str(is_assembly_flag.loc[_idx]).upper() not in {"Y", "YES", "1"}:
                continue
            if _idx[1] not in _target_codes:
                continue
            _ap = float(asm_good_prev.loc[_idx])
            _emit_issue2(
                f"[PREV_DAY_ISSUE] assembly_prev_day 반영 직전(재색인 후 asm_good_prev) "
                f"product={_idx[0]!r} process_code={_idx[1]!r} ap={_ap}",
            )

    # 생산진척현황 행 생성
    prod_rows: list[dict[str, Any]] = []
    for prod, code in sorted_idx:
        idx = (prod, code)
        mp = float(month_plan.reindex(idx_all, fill_value=0.0).loc[idx])
        pp = float(prev_plan.reindex(idx_all, fill_value=0.0).loc[idx])
        gc = float(good_cum.loc[idx])
        gp = float(good_prev.loc[idx])

        group = str(proc_group.loc[idx]) if idx in proc_group.index else ""
        name = str(proc_name.loc[idx]) if idx in proc_name.index else code

        # 특이사항: 기본은 "정상", 계획 미달/지연 시 상태값 변경(단순 로직)
        if pp > 0 and gc < pp:
            status = "미달"
        elif mp > 0 and gc < mp and base_date >= prev_date:
            status = "지연"
        else:
            status = "정상"

        prod_rows.append(
            {
                "product": prod,
                "process_group": group or settings.front_group_name,
                "process_name": name,
                "month_plan": mp,
                "prev_day_plan": pp,
                "cumulative_actual": gc,
                "progress_day": 0.0 if pp <= 0 else (gc / pp) * 100.0,
                "progress_month": 0.0 if mp <= 0 else (gc / mp) * 100.0,
                "prev_day_actual": gp,
                "remark": status,
            }
        )

    # 조립 공정 불량 행 생성 (조립공정만 필터)
    asm_rows: list[dict[str, Any]] = []
    manual_written_for_group: set[tuple[str, str]] = set()
    for prod, code in sorted_idx:
        idx = (prod, code)
        if str(is_assembly_flag.loc[idx]).upper() not in {"Y", "YES", "1"}:
            continue

        group = str(proc_group.loc[idx]) if idx in proc_group.index else ""
        name = str(proc_name.loc[idx]) if idx in proc_name.index else code

        ac = float(asm_good_cum.loc[idx])
        ap = float(asm_good_prev.loc[idx])
        dc = float(asm_def_cum.loc[idx])
        dp = float(asm_def_prev.loc[idx])
        types = str(def_types.loc[idx]) if (idx in def_types.index and def_types.loc[idx]) else ""
        manual_key = (prod, group)
        manual = defect_manual_joined.get(manual_key, "").strip()
        if manual and manual_key in manual_written_for_group:
            manual = ""
        if manual:
            manual_written_for_group.add(manual_key)
        defect_cumulative_types = (types + "\n[수기]\n" + manual) if manual else types

        asm_rows.append(
            {
                "product": prod,
                "process_group": group or settings.backend_group_name,
                "process_name": name,
                "assembly_cumulative": ac,
                "assembly_prev_day": ap,
                "defect_prev_day_count": dp,
                "defect_prev_day_ppm": _ppm(dp, ap),
                "defect_cumulative_count": dc,
                "defect_cumulative_ppm": _ppm(dc, ac),
                "defect_cumulative_types": defect_cumulative_types,
            }
        )

    _asm_dc_sum = sum(float(r["defect_cumulative_count"]) for r in asm_rows)
    _log.info(
        "조립공정불량: 매 요청 신규 집계 (전역 누적 없음) defect_cumulative 합=%s 행=%s "
        "작업일보(기준일까지)행=%s 전일파일행=%s",
        _asm_dc_sum,
        len(asm_rows),
        len(df_today_upto),
        len(df_prev_day),
    )

    # 값이 없으면 '-' 또는 0 처리 (프론트에서 포맷팅 가능하도록 기본값 유지)

    # 상단 요약 텍스트
    month_label_clean = month_label or ""
    summary_title = ""
    if month_label_clean and month_total is not None:
        summary_title = f"1. 생산진척현황 : {month_label_clean} 생산계획(GOC) : {int(month_total):,}ea"

    # 진단용 로그(엑셀과 값이 다를 때 비교에 도움)
    warnings.append(
        f"진단: 누적 집계 rows={len(df_today_upto):,}, 전일 집계 rows={len(df_prev_day):,}, master rows={len(df_master):,}, plan rows={len(df_plan):,}"
    )

    _log.info(
        "[compute_tables] 정상 완료 base_date=%s 생산진척현황_rows=%s 조립공정불량_rows=%s",
        base_date,
        len(prod_rows),
        len(asm_rows),
    )

    return {
        "meta": {
            "base_date": base_date,
            "prev_date": prev_date,
            "warnings": warnings,
            "detected_sheets_today": list(today_sheets.keys()),
            "detected_sheets_prev": list(today_sheets.keys()),
            "month_label": month_label_clean,
            "month_plan_total": month_total,
            "summary_title": summary_title,
        },
        "생산진척현황": prod_rows,
        "조립공정불량": asm_rows,
    }

