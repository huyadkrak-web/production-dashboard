/**
 * 공정불량 자동화(주차·월·LOT) 차트: 불량명 → 색상 전역 매핑.
 * 동일 불량명은 항상 동일 색(고정 맵 또는 결정적 해시 + fallback 팔레트).
 */

/** 총 불량률(ppm) 라인 — 막대 팔레트와 겹치지 않게 별도 유지 */
export const DEFECT_TOTAL_PPM_LINE_COLOR = "#335B99";

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

/** 주요 불량명 고정 색(주차·월·LOT·범례·PDF·대시보드 공통, 최종 palette) */
export const DEFECT_COLOR_MAP: Readonly<Record<string, string>> = {
  "chip crack": "#8878CD",
  "pkg broken": "#4F9AD6",
  "die shift": "#43B581",
  "pcb dent": "#DF75D6",
  "pcb scratch": "#D96BA0",
  "원자재 불량": "#9C8C7A",
  "lead open": "#5C5188",
  "pkg 낙석": "#6478FF",
  "단자 scratch": "#78D3F8",
  "부풀음": "#65789B",
  "pcb 찢어짐": "#6464CD",
  "pad 오염": "#B232B2",
  "단자 오염": "#C2CBD5",
};

/** 고정 맵에 없는 불량명 — 최종 fallback(불투명 solid, `getDefectColor` 순환) */
export const EXTRA_DEFECT_COLORS: readonly string[] = [
  "#5B8FF9",
  "#61DDAA",
  "#65789B",
  "#F6BD16",
  "#7262FD",
  "#78D3F8",
  "#9661BC",
  "#F6903D",
  "#008685",
  "#F78BB4",
  "#C2CBD5",
  "#6DC8EC",
  "#9270CA",
  "#FF9D4D",
  "#269A99",
];

export const DEFECT_FALLBACK_PALETTE: readonly string[] = EXTRA_DEFECT_COLORS;

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
 * `DEFECT_COLOR_MAP` → 없으면 `EXTRA_DEFECT_COLORS` / `DEFECT_FALLBACK_PALETTE`에서 해시 기준 선택(Math.random 없음).
 */
export function getDefectColor(defectName: string): string {
  const key = normalizeDefectNameForColor(defectName);
  if (!key) return "#64748b";
  const fixed = resolveFixedColor(key);
  if (fixed) return fixed;
  return pickFallbackColor(key);
}
