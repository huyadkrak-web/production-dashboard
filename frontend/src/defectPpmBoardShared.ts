import type {
  MonthlyDefectPpmDefectItem,
  MonthlyDefectPpmRow,
  WeeklyDefectPpmDefectItem,
  WeeklyDefectPpmRow,
} from "./api";

/** 구 PPM-only JSON을 건수로 승격할 때 쓰는 가상 출하량(1e6이면 count ≒ 기존 ppm 값) */
export const LEGACY_PPM_ASSUMED_AO_QTY = 1_000_000;

/** 레거시 컬럼 → 표시용 불량명 (기존 JSON·데모 호환) */
export const LEGACY_DEFECT_COLUMNS: { key: string; label: string }[] = [
  { key: "chip_crack", label: "Chip Crack" },
  { key: "die_shift", label: "Die Shift" },
  { key: "pad_open", label: "Pad Open" },
  { key: "lead_open", label: "Lead Open" },
  { key: "pad_contam", label: "Pad 오염" },
  { key: "lead_contam", label: "Lead 오염" },
  { key: "scratch", label: "Scratch" },
  { key: "pkg_nakseok", label: "PKG 낙석" },
  { key: "sawing_miss", label: "Sawing Miss" },
  { key: "mk_defect", label: "M/K불량" },
  { key: "pkg_broken", label: "PKG Broken" },
  { key: "etc", label: "기타" },
];

const LEGACY_SUM_DEFECT_NAMES = new Set(["합산(기존)", "합산"]);

export type WeeklyRowUi = {
  week: string;
  ao_qty: number;
  defect_total: number;
  /** 컬럼 순서와 동일한 불량 건수 */
  defectValues: number[];
};

export type MonthlyRowUi = {
  label: string;
  total_ppm: number;
  defectValues: number[];
};

/**
 * PPM 화면 표시 전용: 반올림 정수 + ko-KR 천 단위 구분.
 * 차트(Y축·LabelList)·툴팁·주차별 불량율(PPM) 열 등 주차/월별 PPM UI에서 공통 사용.
 * (내부 chartData·저장값의 실수는 그대로 두고 표시만 정수화)
 */
export function formatPpmKr(value: number): string {
  if (!Number.isFinite(value)) return "";
  return Math.round(value).toLocaleString("ko-KR");
}

export function num(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** ppm 수치와 분모 ao_qty로 역산한 불량 건수(반올림, 음수 방지) */
export function ppmToCount(ppm: unknown, aoQty: unknown): number {
  const ao = num(aoQty);
  if (ao <= 0) return Math.max(0, Math.round(num(ppm)));
  return Math.max(0, Math.round((num(ppm) / 1_000_000) * ao));
}

export function sumWeeklyDefectCounts(defects: readonly WeeklyDefectPpmDefectItem[]): number {
  return defects.reduce((s, d) => s + num(d.count), 0);
}

export function sumMonthlyDefectValues(defects: readonly MonthlyDefectPpmDefectItem[]): number {
  return defects.reduce((s, d) => s + num(d.value), 0);
}

function defectJsonItemIsCountBased(it: unknown): boolean {
  if (!it || typeof it !== "object") return false;
  const o = it as Record<string, unknown>;
  if (!Object.prototype.hasOwnProperty.call(o, "count")) return false;
  if (o.count === undefined || o.count === null) return false;
  return true;
}

function defectsArrayIsCountBased(defects: unknown[]): boolean {
  return defects.length > 0 && defects.every(defectJsonItemIsCountBased);
}

/**
 * 주차 defects[] 항목 파싱. `count` 우선, 없으면 레거시 `value`(PPM)를 ao 기준으로 건수로 환산.
 */
export function parseWeeklyDefectItemFromUnknown(item: unknown, aoQtyForValueMigration: number): WeeklyDefectPpmDefectItem {
  if (!item || typeof item !== "object") {
    return { name: "", count: 0 };
  }
  const o = item as Record<string, unknown>;
  const name = String(o.name ?? "").trim();
  if (defectJsonItemIsCountBased(item)) {
    return { name, count: Math.max(0, Math.round(num(o.count))) };
  }
  const ppmVal = num(o.value);
  const ao =
    num(aoQtyForValueMigration) > 0 ? num(aoQtyForValueMigration) : LEGACY_PPM_ASSUMED_AO_QTY;
  return { name, count: ppmToCount(ppmVal, ao) };
}

export function parseMonthlyDefectItemFromUnknown(item: unknown): MonthlyDefectPpmDefectItem {
  if (!item || typeof item !== "object") {
    return { name: "", value: 0 };
  }
  const o = item as Record<string, unknown>;
  return {
    name: String(o.name ?? "").trim(),
    value: num(o.value),
  };
}

export function migrateLegacyFlatToMonthlyDefects(r: Record<string, unknown>): MonthlyDefectPpmDefectItem[] {
  const etcName = String(r.etc_name ?? "").trim();
  const out: MonthlyDefectPpmDefectItem[] = [];
  for (const { key, label } of LEGACY_DEFECT_COLUMNS) {
    const v = num(r[key]);
    if (v === 0) continue;
    if (key === "etc") {
      out.push({ name: etcName || "기타", value: v });
    } else {
      out.push({ name: label, value: v });
    }
  }
  return out;
}

/** 플랫 레거시(각 필드가 PPM) → 건수. ao_qty가 있으면 그 분모로, 없으면 LEGACY_PPM_ASSUMED_AO_QTY */
export function migrateLegacyFlatToWeeklyCounts(r: Record<string, unknown>): WeeklyDefectPpmDefectItem[] {
  const ao =
    Object.prototype.hasOwnProperty.call(r, "ao_qty") && num(r.ao_qty) > 0
      ? num(r.ao_qty)
      : LEGACY_PPM_ASSUMED_AO_QTY;
  const etcName = String(r.etc_name ?? "").trim();
  const out: WeeklyDefectPpmDefectItem[] = [];
  for (const { key, label } of LEGACY_DEFECT_COLUMNS) {
    const ppmV = num(r[key]);
    if (ppmV === 0) continue;
    if (key === "etc") {
      out.push({ name: etcName || "기타", count: ppmToCount(ppmV, ao) });
    } else {
      out.push({ name: label, count: ppmToCount(ppmV, ao) });
    }
  }
  return out;
}

export function mergeLegacyEtcIntoMonthlyDefects(
  defects: MonthlyDefectPpmDefectItem[],
  r: Record<string, unknown>,
): MonthlyDefectPpmDefectItem[] {
  const legacyEtc = num(r.etc);
  if (legacyEtc === 0) return defects;
  const en = String(r.etc_name ?? "").trim();
  return [...defects, { name: en || "기타", value: legacyEtc }];
}

export function mergeLegacyEtcIntoWeeklyCounts(
  defects: WeeklyDefectPpmDefectItem[],
  r: Record<string, unknown>,
  aoQtyForEtcPpm: number,
): WeeklyDefectPpmDefectItem[] {
  const legacyEtcPpm = num(r.etc);
  if (legacyEtcPpm === 0) return defects;
  const en = String(r.etc_name ?? "").trim();
  const ao = num(aoQtyForEtcPpm) > 0 ? num(aoQtyForEtcPpm) : LEGACY_PPM_ASSUMED_AO_QTY;
  return [...defects, { name: en || "기타", count: ppmToCount(legacyEtcPpm, ao) }];
}

/** 예전 월별 등에서 쓰이던 의사 불량명 "합산(기존)" 제거 — 값은 total_ppm 복구용으로만 사용 */
export function stripLegacySumNamedDefects(defects: MonthlyDefectPpmDefectItem[]): {
  defects: MonthlyDefectPpmDefectItem[];
  legacySumPpm: number;
} {
  let legacySumPpm = 0;
  const next = defects.filter((x) => {
    const n = String(x.name ?? "").trim();
    if (LEGACY_SUM_DEFECT_NAMES.has(n)) {
      legacySumPpm += num(x.value);
      return false;
    }
    return true;
  });
  return { defects: next, legacySumPpm };
}

export function normalizeWeeklyDefectPpmRow(r: Record<string, unknown>): WeeklyDefectPpmRow {
  const week = String(r.week ?? "").trim();
  const aoKeyPresent = Object.prototype.hasOwnProperty.call(r, "ao_qty");
  let ao_qty = aoKeyPresent ? num(r.ao_qty) : 0;

  const isFlatLegacy = !Array.isArray(r.defects);
  let defects: WeeklyDefectPpmDefectItem[];

  if (Array.isArray(r.defects)) {
    const arr = r.defects as unknown[];
    const aoForParsing = ao_qty > 0 ? ao_qty : LEGACY_PPM_ASSUMED_AO_QTY;
    defects = arr.map((it) => parseWeeklyDefectItemFromUnknown(it, aoForParsing));
    defects = mergeLegacyEtcIntoWeeklyCounts(defects, r, aoForParsing);
  } else {
    defects = migrateLegacyFlatToWeeklyCounts(r);
  }

  const countBased = Array.isArray(r.defects) && defectsArrayIsCountBased(r.defects as unknown[]);
  const needsLegacyAo =
    ao_qty <= 0 &&
    !countBased &&
    (isFlatLegacy ||
      num(r.total_ppm) > 0 ||
      (Array.isArray(r.defects) && (r.defects as unknown[]).some((it) => !defectJsonItemIsCountBased(it))));

  if (needsLegacyAo) {
    ao_qty = LEGACY_PPM_ASSUMED_AO_QTY;
  }

  const sumCounts = sumWeeklyDefectCounts(defects);
  const dtKeyPresent = Object.prototype.hasOwnProperty.call(r, "defect_total");
  let defect_total = dtKeyPresent ? num(r.defect_total) : NaN;
  if (!Number.isFinite(defect_total) || !dtKeyPresent) {
    const legacyTotalPpm = num(r.total_ppm);
    if (legacyTotalPpm > 0) {
      defect_total = ppmToCount(legacyTotalPpm, ao_qty);
    } else {
      defect_total = sumCounts;
    }
  }
  if (defect_total <= 0 && sumCounts > 0) {
    defect_total = sumCounts;
  }

  return { week, ao_qty, defect_total, defects };
}

export function normalizeMonthlyDefectPpmRow(r: Record<string, unknown>): MonthlyDefectPpmRow {
  const label = String(r.label ?? r.month ?? "").trim();
  const legacyPpm = num(r.ppm);

  let defects: MonthlyDefectPpmDefectItem[];
  let legacySumPpm = 0;

  if (Array.isArray(r.defects)) {
    defects = (r.defects as unknown[]).map(parseMonthlyDefectItemFromUnknown);
    defects = mergeLegacyEtcIntoMonthlyDefects(defects, r);
    const st = stripLegacySumNamedDefects(defects);
    defects = st.defects;
    legacySumPpm = st.legacySumPpm;
  } else {
    defects = migrateLegacyFlatToMonthlyDefects(r);
    const st = stripLegacySumNamedDefects(defects);
    defects = st.defects;
    legacySumPpm = st.legacySumPpm;
  }

  const sumD = sumMonthlyDefectValues(defects);
  let total_ppm = num(r.total_ppm);
  if (!Number.isFinite(total_ppm)) total_ppm = 0;
  if (total_ppm === 0 && legacySumPpm > 0) {
    total_ppm = legacySumPpm;
  }
  if (!Array.isArray(r.defects) && total_ppm === 0 && sumD > 0) {
    total_ppm = sumD;
  }
  if (defects.length === 0 && sumD === 0 && total_ppm === 0 && legacyPpm > 0) {
    total_ppm = legacyPpm;
  }
  return { label, defects, total_ppm };
}

/** ISO 주차의 월요일 00:00 UTC (isoWeek: 1..53, isoWeekYear: 달력 연도 기준으로 ISO 주차 연도에 사용) */
function utcMondayOfIsoWeek(isoWeekYear: number, isoWeek: number): Date {
  const jan4 = new Date(Date.UTC(isoWeekYear, 0, 4));
  const isoDow = jan4.getUTCDay() || 7;
  const mondayW1 = new Date(jan4);
  mondayW1.setUTCDate(jan4.getUTCDate() - isoDow + 1);
  const out = new Date(mondayW1);
  out.setUTCDate(mondayW1.getUTCDate() + (isoWeek - 1) * 7);
  return out;
}

/**
 * 주차 문자열 → 출하 월 라벨 (`26.4` = 2026년 4월).
 * - 이미 `yy.m` 형태면 정규화해 반환
 * - `WW16`, `W03`, `ww16` 등은 `referenceIsoYear`(기본 UTC 현재 연도) 기준 ISO 주차 → 해당 월의 yy.m
 * - 매핑 불가 시 null (집계에서 제외)
 */
export function weekToShipmentMonthLabel(
  week: string,
  referenceIsoYear?: number,
): string | null {
  const w = String(week ?? "").trim();
  if (!w) return null;

  const yyDotM = /^(\d{2})\.(\d{1,2})$/.exec(w);
  if (yyDotM) {
    const yy = yyDotM[1];
    const m = String(Number(yyDotM[2]));
    return `${yy}.${m}`;
  }

  const ww = /^WW\s*(\d+)$/i.exec(w) ?? /^W\s*(\d+)$/i.exec(w);
  if (!ww) return null;
  const weekNum = Number(ww[1]);
  if (!Number.isFinite(weekNum) || weekNum < 1 || weekNum > 53) return null;

  const year =
    referenceIsoYear != null && Number.isFinite(referenceIsoYear) && referenceIsoYear > 0
      ? Math.trunc(referenceIsoYear)
      : new Date().getUTCFullYear();

  const mon = utcMondayOfIsoWeek(year, weekNum);
  const month = mon.getUTCMonth() + 1;
  const yy = year % 100;
  return `${yy}.${month}`;
}

/** 월 라벨 `yy.m` 시간순 정렬 키 (알 수 없는 라벨은 맨 뒤) */
export function monthLabelChronologicalSortKey(label: string): number {
  const m = /^(\d+)\.(\d+)$/.exec(String(label).trim());
  if (!m) return Number.MAX_SAFE_INTEGER;
  return Number(m[1]) * 100 + Number(m[2]);
}

/** `yy.m` 다음 달 라벨 (99.12 → 0.1). 파싱 불가 시 null */
export function nextYyDotMonthLabel(label: string): string | null {
  const m = /^(\d{1,2})\.(\d{1,2})$/.exec(String(label).trim());
  if (!m) return null;
  let yy = Number(m[1]);
  let mo = Number(m[2]);
  if (!Number.isFinite(yy) || !Number.isFinite(mo)) return null;
  mo += 1;
  if (mo > 12) {
    mo = 1;
    yy = (yy + 1) % 100;
  }
  return `${yy}.${mo}`;
}

/** `WWnn` 또는 `Wnn` 파싱(1..53). 실패 시 null */
function parseWeekLabelToNumber(label: string): number | null {
  const m = /^WW\s*(\d+)$/i.exec(String(label).trim()) ?? /^W\s*(\d+)$/i.exec(String(label).trim());
  if (!m) return null;
  const n = Number(m[1]);
  if (!Number.isFinite(n) || n < 1 || n > 53) return null;
  return n;
}

/** 다음 주차 라벨(`WW53` 다음은 `WW01`) */
export function nextWeekLabel(label: string): string | null {
  const n = parseWeekLabelToNumber(label);
  if (n == null) return null;
  const nn = n >= 53 ? 1 : n + 1;
  return `WW${String(nn).padStart(2, "0")}`;
}

/** 주차 라벨 `WWnn` 시간순 정렬 키 (알 수 없는 라벨은 맨 뒤) */
export function weekLabelChronologicalSortKey(label: string): number {
  const n = parseWeekLabelToNumber(label);
  if (n == null) return Number.MAX_SAFE_INTEGER;
  return n;
}

/**
 * 주차 차트 X축용: 실제 주차 라벨만 정렬한 뒤, 개수가 `minCount` 미만이면
 * 마지막 실제 주차부터 미래 주차만 채움(가짜 주차, 차트는 null).
 * `minCount` 이상이면 실제 라벨만 그대로 반환.
 */
export function padWeeklyLabelsForChartAxis(
  realWeekLabels: readonly string[],
  minCount = 3,
): string[] {
  const seen = new Set<string>();
  const sorted = [...realWeekLabels]
    .map((s) => String(s ?? "").trim())
    .filter((t) => {
      if (!t) return false;
      const n = parseWeekLabelToNumber(t);
      if (n == null) return false;
      const norm = `WW${String(n).padStart(2, "0")}`;
      if (seen.has(norm)) return false;
      seen.add(norm);
      return true;
    })
    .sort((a, b) => weekLabelChronologicalSortKey(a) - weekLabelChronologicalSortKey(b));

  if (sorted.length === 0) return [];
  if (sorted.length >= minCount) return sorted;

  const out = [...sorted];
  while (out.length < minCount) {
    const last = out[out.length - 1]!;
    const nx = nextWeekLabel(last);
    if (!nx || seen.has(nx)) break;
    seen.add(nx);
    out.push(nx);
  }
  return out;
}

/**
 * 월별 차트 X축용: 실제 데이터 월만 정렬한 뒤, 개수가 `minCount` 미만이면
 * 마지막 실제 월부터 `nextYyDotMonthLabel`로 미래 월 라벨만 채움(가짜 월, 차트는 null).
 * `minCount` 이상이면 실제 라벨만 그대로 반환.
 */
export function padMonthlyLabelsForChartAxis(
  realMonthLabels: readonly string[],
  minCount = 3,
): string[] {
  const seen = new Set<string>();
  const sorted = [...realMonthLabels]
    .map((s) => String(s ?? "").trim())
    .filter((t) => {
      if (!t || seen.has(t)) return false;
      seen.add(t);
      return true;
    })
    .sort((a, b) => monthLabelChronologicalSortKey(a) - monthLabelChronologicalSortKey(b));

  if (sorted.length === 0) return [];
  if (sorted.length >= minCount) return sorted;

  const out = [...sorted];
  while (out.length < minCount) {
    const last = out[out.length - 1]!;
    const nx = nextYyDotMonthLabel(last);
    if (!nx || seen.has(nx)) break;
    seen.add(nx);
    out.push(nx);
  }
  return out;
}

/** @deprecated use `padMonthlyLabelsForChartAxis` */
export const expandMonthLabelsForChartAxis = padMonthlyLabelsForChartAxis;

/** 월 라벨 `yy.m` 기준 정렬 (알 수 없는 라벨은 맨 뒤) */
export function sortMonthlyDefectRowsByLabel(rows: readonly MonthlyDefectPpmRow[]): MonthlyDefectPpmRow[] {
  return [...rows].sort(
    (a, b) => monthLabelChronologicalSortKey(a.label) - monthLabelChronologicalSortKey(b.label),
  );
}

/** ao_qty>0일 때 불량 건수 → PPM. 분모 없으면 null(차트에서 숨김) */
export function weeklyBarPpmFromCount(ao_qty: unknown, count: unknown): number | null {
  const ao = num(ao_qty);
  if (ao <= 0) return null;
  return (num(count) / ao) * 1_000_000;
}

export function weeklyLinePpmFromTotals(ao_qty: unknown, defect_total: unknown): number | null {
  const ao = num(ao_qty);
  if (ao <= 0) return null;
  return (num(defect_total) / ao) * 1_000_000;
}

/**
 * 여러 주차 행의 count·ao_qty·defect_total을 합산한 뒤, 월별 PPM 보드용 행으로 변환합니다.
 * (월별 JSON은 기존처럼 defects[].value = PPM 유지)
 */
export function weeklyDefectRowsToMonthlyPpmRow(
  label: string,
  rows: readonly WeeklyDefectPpmRow[],
): MonthlyDefectPpmRow {
  let ao = 0;
  let dt = 0;
  const byName = new Map<string, number>();
  for (const row of rows) {
    ao += num(row.ao_qty);
    dt += num(row.defect_total);
    for (const d of row.defects) {
      const n = String(d.name ?? "").trim();
      if (!n) continue;
      byName.set(n, (byName.get(n) ?? 0) + num(d.count));
    }
  }
  const defectOrder = [...byName.keys()];
  const total_ppm = ao > 0 ? (dt / ao) * 1_000_000 : 0;
  const defects: MonthlyDefectPpmDefectItem[] = defectOrder.map((name) => ({
    name,
    value: ao > 0 ? ((byName.get(name) ?? 0) / ao) * 1_000_000 : 0,
  }));
  return { label, defects, total_ppm };
}

/** `week` 문자열을 월 라벨로 매핑합니다. null/빈 문자열이면 해당 행은 제외됩니다. */
export function aggregateWeeklyRowsByMonthLabel(
  rows: readonly WeeklyDefectPpmRow[],
  monthLabelOfWeek: (week: string) => string | null | undefined,
): MonthlyDefectPpmRow[] {
  const groups = new Map<string, WeeklyDefectPpmRow[]>();
  for (const row of rows) {
    const w = String(row.week ?? "").trim();
    const lb = monthLabelOfWeek(w);
    const label = String(lb ?? "").trim();
    if (!label) continue;
    const arr = groups.get(label) ?? [];
    arr.push(row);
    groups.set(label, arr);
  }
  const merged = [...groups.entries()].map(([label, rs]) => weeklyDefectRowsToMonthlyPpmRow(label, rs));
  return sortMonthlyDefectRowsByLabel(merged);
}

/** 레거시(행마다 defects 길이가 다름): 불량명 유니온, 첫 등장 순 */
export function inferDefectColumnNamesUnion<T extends { defects: readonly { name?: string }[] }>(
  rows: readonly T[],
): string[] {
  const seen = new Set<string>();
  const order: string[] = [];
  for (const row of rows) {
    for (const d of row.defects) {
      const n = String(d.name ?? "").trim();
      if (!n) continue;
      if (!seen.has(n)) {
        seen.add(n);
        order.push(n);
      }
    }
  }
  return order;
}

/** 신규 저장(모든 행 defects 길이 동일): 컬럼명을 인덱스별로 복원, 빈 헤더 유지 */
export function inferDefectColumnNamesIndexed<T extends { defects: readonly { name?: string }[] }>(
  rows: readonly T[],
): string[] {
  const maxLen = Math.max(...rows.map((row) => row.defects.length), 0);
  if (maxLen === 0) return [""];
  return Array.from({ length: maxLen }, (_, i) => {
    for (const row of rows) {
      const nm = String(row.defects[i]?.name ?? "").trim();
      if (nm) return nm;
    }
    return "";
  });
}

export function isIndexedDefectLayout<T extends { defects: readonly unknown[] }>(rows: readonly T[]): boolean {
  if (rows.length === 0) return false;
  const len0 = rows[0].defects.length;
  if (len0 === 0) return false;
  return rows.every((r) => r.defects.length === len0);
}

export function alignWeeklyRowToColumns(
  row: WeeklyDefectPpmRow,
  columns: string[],
  indexed: boolean,
): WeeklyRowUi {
  if (indexed) {
    return {
      week: row.week,
      ao_qty: num(row.ao_qty),
      defect_total: num(row.defect_total),
      defectValues: columns.map((_, i) => Math.max(0, Math.round(num(row.defects[i]?.count)))),
    };
  }
  const byName = new Map<string, number>();
  for (const d of row.defects) {
    const n = String(d.name ?? "").trim();
    if (!n) continue;
    byName.set(n, (byName.get(n) ?? 0) + Math.max(0, Math.round(num(d.count))));
  }
  return {
    week: row.week,
    ao_qty: num(row.ao_qty),
    defect_total: num(row.defect_total),
    defectValues: columns.map((c) => byName.get(String(c).trim()) ?? 0),
  };
}

export function alignMonthlyRowToColumns(
  row: MonthlyDefectPpmRow,
  columns: string[],
  indexed: boolean,
): MonthlyRowUi {
  if (indexed) {
    return {
      label: row.label,
      total_ppm: row.total_ppm,
      defectValues: columns.map((_, i) => num(row.defects[i]?.value)),
    };
  }
  const byName = new Map<string, number>();
  for (const d of row.defects) {
    const n = String(d.name ?? "").trim();
    if (!n) continue;
    byName.set(n, (byName.get(n) ?? 0) + num(d.value));
  }
  return {
    label: row.label,
    total_ppm: row.total_ppm,
    defectValues: columns.map((c) => byName.get(String(c).trim()) ?? 0),
  };
}

export function defaultWeeklyUiRow(columnCount: number): WeeklyRowUi {
  return {
    week: "",
    ao_qty: 0,
    defect_total: 0,
    defectValues: Array.from({ length: columnCount }, () => 0),
  };
}

export function defaultMonthlyUiRow(columnCount: number): MonthlyRowUi {
  return {
    label: "",
    total_ppm: 0,
    defectValues: Array.from({ length: columnCount }, () => 0),
  };
}

export function toSaveWeeklyRows(uiRows: WeeklyRowUi[], defectColumnNames: string[]): WeeklyDefectPpmRow[] {
  return uiRows.map((r) => ({
    week: String(r.week ?? "").trim(),
    ao_qty: Math.max(0, Math.round(num(r.ao_qty))),
    defect_total: Math.max(0, Math.round(num(r.defect_total))),
    defects: defectColumnNames.map((name, i) => ({
      name: String(name ?? "").trim(),
      count: Math.max(0, Math.round(num(r.defectValues[i]))),
    })),
  }));
}

export function toSaveMonthlyRows(uiRows: MonthlyRowUi[], defectColumnNames: string[]): MonthlyDefectPpmRow[] {
  return uiRows.map((r) => ({
    label: String(r.label ?? "").trim(),
    total_ppm: num(r.total_ppm),
    defects: defectColumnNames.map((name, i) => ({
      name: String(name ?? "").trim(),
      value: num(r.defectValues[i]),
    })),
  }));
}

export function chartDataKeyAt(index: number): string {
  return `__def${index}`;
}

export function isNullishChartNumber(v: unknown): boolean {
  return v == null || (typeof v === "number" && !Number.isFinite(v));
}

/** 월별 PPM 보드: 총 PPM·스택 불량이 모두 0이면 차트에는 데이터 없음(null) */
export function rowHasNoChartableMonthlyPpm(
  r: { total_ppm: number; defectValues: number[] },
  chartColumnIndices: number[],
): boolean {
  if (num(r.total_ppm) !== 0) return false;
  const stackSum = chartColumnIndices.reduce((s, colIdx) => s + num(r.defectValues[colIdx]), 0);
  return stackSum === 0;
}

/**
 * 주차별: ao_qty<=0 이면 차트 비움(null).
 * ao>0이면 PPM으로 환산했을 때 총선·스택이 모두 0이면 기존과 같이 비움(null).
 */
export function rowHasNoChartableWeeklyPpm(
  r: { ao_qty: number; defect_total: number; defectValues: number[] },
  chartColumnIndices: number[],
): boolean {
  const ao = num(r.ao_qty);
  if (ao <= 0) return true;
  const linePpm = weeklyLinePpmFromTotals(ao, r.defect_total);
  if (linePpm != null && linePpm !== 0) return false;
  const stackSumPpm = chartColumnIndices.reduce((s, colIdx) => {
    const p = weeklyBarPpmFromCount(ao, r.defectValues[colIdx]);
    return s + (p == null ? 0 : p);
  }, 0);
  return stackSumPpm === 0;
}

// --- /defect-auto/compute → 주·월 보드 수동 병합(같은 week/label 덮어쓰기) ---

/**
 * API 월 집계 행(월 키·건수·ao) → 월별 PPM 보드 ``MonthlyDefectPpmRow``(defects[].value = 품목 PPM).
 */
export function apiMonthlyItemToMonthlyPpmRow(item: {
  month: string;
  ao_qty: unknown;
  defect_total: unknown;
  defects?: readonly { name?: unknown; count?: unknown }[];
}): MonthlyDefectPpmRow {
  const wk: WeeklyDefectPpmRow = {
    week: "__api__",
    ao_qty: num(item.ao_qty),
    defect_total: num(item.defect_total),
    defects: (item.defects ?? []).map((d) => ({
      name: String(d.name ?? "").trim(),
      count: Math.max(0, Math.round(num((d as { count?: unknown }).count))),
    })),
  };
  return weeklyDefectRowsToMonthlyPpmRow(String(item.month ?? "").trim(), [wk]);
}

/** ``unknown[]`` (API ``monthly``) → ``MonthlyDefectPpmRow[]`` */
export function parseDefectApiMonthlyItems(rows: unknown[]): MonthlyDefectPpmRow[] {
  const out: MonthlyDefectPpmRow[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const o = row as Record<string, unknown>;
    const label = String(o.month ?? o.label ?? "").trim();
    if (!label) continue;
    out.push(
      apiMonthlyItemToMonthlyPpmRow({
        month: label,
        ao_qty: o.ao_qty,
        defect_total: o.defect_total,
        defects: o.defects as { name: string; count: number }[] | undefined,
      }),
    );
  }
  return out;
}

/**
 * 주차 보드: 동일 ``week`` 키는 API 행으로 덮어쓰고, 나머지 수기 행은 유지. 불량 컬럼은 합집합.
 */
export function mergeWeeklyDefectPpmData(
  existingRows: WeeklyRowUi[],
  defectColumnNames: string[],
  incomingRaw: readonly unknown[],
): { cols: string[]; rows: WeeklyRowUi[] } {
  const incoming = incomingRaw
    .map((row) => normalizeWeeklyDefectPpmRow(row as Record<string, unknown>))
    .filter((r) => String(r.week ?? "").trim() !== "");
  if (incoming.length === 0) {
    return { cols: defectColumnNames, rows: existingRows };
  }
  const existingSave = toSaveWeeklyRows(existingRows, defectColumnNames);
  const incomingKeys = new Set(incoming.map((r) => String(r.week).trim()));
  const kept = existingSave.filter((r) => !incomingKeys.has(String(r.week).trim()));
  const merged = [...kept, ...incoming];
  const indexed = isIndexedDefectLayout(merged);
  const inf = indexed
    ? inferDefectColumnNamesIndexed(merged)
    : inferDefectColumnNamesUnion(merged);
  const finalCols = inf.length > 0 ? inf : [""];
  const ui = merged.map((r) => alignWeeklyRowToColumns(r, finalCols, indexed));
  return { cols: finalCols, rows: ui };
}

/**
 * 월별 보드: 동일 ``label``(월)은 API 합집계 행으로 덮어쓰고, 나머지 수기 행은 유지.
 */
export function mergeMonthlyDefectPpmData(
  existingRows: MonthlyRowUi[],
  defectColumnNames: string[],
  incomingPpmRows: readonly MonthlyDefectPpmRow[],
): { cols: string[]; rows: MonthlyRowUi[] } {
  if (incomingPpmRows.length === 0) {
    return { cols: defectColumnNames, rows: existingRows };
  }
  const existingSave = toSaveMonthlyRows(existingRows, defectColumnNames);
  const incomingKeys = new Set(
    incomingPpmRows.map((r) => String(r.label ?? "").trim()),
  );
  const kept = existingSave.filter((r) => !incomingKeys.has(String(r.label).trim()));
  const merged = sortMonthlyDefectRowsByLabel([...kept, ...incomingPpmRows]);
  const inf = inferDefectColumnNamesUnion(merged);
  const finalCols = inf.length > 0 ? inf : [""];
  const ui = merged.map((r) => alignMonthlyRowToColumns(r, finalCols, false));
  return { cols: finalCols, rows: ui };
}
