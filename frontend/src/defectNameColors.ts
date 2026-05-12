/**
 * 공정불량 자동화(주차·월·LOT) 차트: 불량명 → 색상 전역 매핑.
 * 동일 불량명은 항상 동일 색(고정 맵 또는 결정적 해시 + fallback 팔레트).
 */

/** 총 불량률(ppm) 라인 — 막대 팔레트와 겹치지 않게 별도 유지 */
export const DEFECT_TOTAL_PPM_LINE_COLOR = "#2C5AA0";

/** 비교·키용 정규화: trim, 연속 공백 축소, NFKC, 영문 소문자 */
export function normalizeDefectNameForColor(raw: string): string {
  let s = String(raw ?? "")
    .trim()
    .replace(/\s+/g, " ");
  try {
    s = s.normalize("NFKC");
  } catch {
    /* ignore */
  }
  return s.toLowerCase();
}

function normalizeHex(hex: string): string {
  return String(hex ?? "")
    .trim()
    .toUpperCase();
}

/** 주요 불량명 고정 색(주차·월·LOT·범례·PDF 공통) */
export const DEFECT_COLOR_MAP: Readonly<Record<string, string>> = {
  "chip crack": "#6C5CE7",
  "pkg broken": "#3498DB",
  "die shift": "#00B894",
  "pcb dent": "#E67E22",
  "pcb scratch": "#E84393",
  "원자재 불량": "#8E6E53",
  "lead open": "#F1C40F",
  "pkg 낙석": "#9B59B6",
  "단자 scratch": "#5DADE2",
  "부풀음": "#27AE60",
  "pad 오염": "#E74C3C",
  "pcb 찢어짐": "#1ABC9C",
  "단자 오염": "#FD79A8",
};

/** 고정 맵에 없는 불량명 — 파스텔·선명색 혼합, 결정적 배정 */
export const DEFECT_FALLBACK_PALETTE: readonly string[] = [
  "#2E86DE",
  "#F39C12",
  "#16A085",
  "#D35400",
  "#7D3C98",
  "#C0392B",
  "#00CEC9",
  "#A29BFE",
  "#FAB1A0",
  "#55EFC4",
  "#74B9FF",
  "#FFEAA7",
  "#E17055",
  "#6AB04C",
  "#BE2EDD",
  "#FF7675",
  "#0984E3",
  "#FDCB6E",
  "#00B894",
  "#E84393",
];

const RESERVED_HEX_FOR_FALLBACK: ReadonlySet<string> = (() => {
  const s = new Set<string>();
  for (const v of Object.values(DEFECT_COLOR_MAP)) {
    s.add(normalizeHex(v));
  }
  s.add(normalizeHex(DEFECT_TOTAL_PPM_LINE_COLOR));
  return s;
})();

function fnv1a32(str: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

function resolveFixedColor(normalized: string): string | undefined {
  if (!normalized) return undefined;
  const direct = DEFECT_COLOR_MAP[normalized];
  if (direct) return direct;
  const compact = normalized.replace(/\s/g, "");
  for (const [k, v] of Object.entries(DEFECT_COLOR_MAP)) {
    if (k.replace(/\s/g, "").toLowerCase() === compact) return v;
  }
  return undefined;
}

function pickFallbackColor(normalizedKey: string): string {
  const n = DEFECT_FALLBACK_PALETTE.length;
  if (n === 0) return "#64748b";
  const h1 = fnv1a32(normalizedKey);
  const h2 = fnv1a32(`${normalizedKey}\u0007defect-fallback`);
  const start = (h1 ^ h2) % n;
  for (let j = 0; j < n; j++) {
    const c = DEFECT_FALLBACK_PALETTE[(start + j) % n]!;
    if (!RESERVED_HEX_FOR_FALLBACK.has(normalizeHex(c))) {
      return c;
    }
  }
  return DEFECT_FALLBACK_PALETTE[start % n]!;
}

/**
 * 불량명에 대한 차트·범례·막대 fill 색상(hex).
 * `DEFECT_COLOR_MAP` → 없으면 `DEFECT_FALLBACK_PALETTE`에서 해시 기준 선택(Math.random 없음).
 */
export function getDefectColor(defectName: string): string {
  const key = normalizeDefectNameForColor(defectName);
  if (!key) return "#64748b";
  const fixed = resolveFixedColor(key);
  if (fixed) return fixed;
  return pickFallbackColor(key);
}
