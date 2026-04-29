/** 주차별 불량 PPM 차트·PDF 범례에서 공유하는 팔레트·빌더 */

/** PDF·고정폭 캡처용 캔버스 너비 — 주차·월별 동일 */
export const DEFECT_PPM_FIXED_CHART_WIDTH = 1150;

/** 주차·월별 ComposedChart `margin` 동일 */
export const DEFECT_PPM_COMPOSED_CHART_MARGIN = { top: 28, right: 14, left: 8, bottom: 22 } as const;

/** 막대 스택 영역 높이(px) — 주차·월별 동일 */
export const DEFECT_PPM_PLOT_HEIGHT = 430;

/** 생산일보 PDF 1페이지: `App.tsx` `PDF_ONE_PAGE_ROOT_STYLE.width` 와 동일 */
export const PDF_ONE_PAGE_ROOT_WIDTH_PX = 1320;

/** `App.tsx` `PDF_ONE_PAGE_INNER_STYLE` 좌우(및 상하) padding px */
export const PDF_ONE_PAGE_INNER_PADDING_PX = 8;

/**
 * 1페이지 루트 안 콘텐츠 가로(`ROOT` − inner padding×2) — 월별 `section.card`가 차지하는 폭과 동일.
 */
export const PDF_ONE_PAGE_CHART_CARD_INNER_WIDTH_PX =
  PDF_ONE_PAGE_ROOT_WIDTH_PX - PDF_ONE_PAGE_INNER_PADDING_PX * 2;

/**
 * `.pdf-export-mode .card` 좌우 padding 18px×2(`styles.css`) — 카드 본문(차트) 실질 가로.
 * 월별 1페이지 차트 플레이스홀더 내부 가로와 동일.
 */
export const PDF_ONE_PAGE_CARD_HORIZONTAL_PADDING_PX = 18 * 2;

export const PDF_ONE_PAGE_CARD_BODY_CONTENT_WIDTH_PX =
  PDF_ONE_PAGE_CHART_CARD_INNER_WIDTH_PX - PDF_ONE_PAGE_CARD_HORIZONTAL_PADDING_PX;

/** 1150×430 기준을 다른 가로폭에 맞춰 비율 보존(1페이지 월별 img `width:100%` 스케일과 동일 비율). */
export function defectPpmPlotHeightForWidthPx(widthPx: number): number {
  return Math.round(DEFECT_PPM_PLOT_HEIGHT * (widthPx / DEFECT_PPM_FIXED_CHART_WIDTH));
}

export const WEEKLY_DEFECT_STACK_COLORS = [
  "#4E79A7",
  "#76B7B2",
  "#59A14F",
  "#EDC948",
  "#F28E2B",
  "#E15759",
  "#B07AA1",
  "#9C755F",
  "#BAB0AC",
];

export const WEEKLY_TOTAL_PPM_LINE_COLOR = "#2F5597";

export type WeeklyPdfLegendEntry = {
  label: string;
  color: string;
  variant: "bar" | "line";
};

/**
 * 주차별·월별 불량 PPM 막대 차트 공통.
 * 카테고리가 많을수록 %를 낮춰 같은 차트 폭 안에서 막대가 자연스럽게 가늘어지게 함.
 * 막대 폭은 Recharts 기본 + `barCategoryGap`만 사용(Bar에 `maxBarSize`/`barSize`는 두지 않음).
 */
export function defectPpmBarCategoryGap(categoryCount: number): string {
  if (categoryCount <= 0) return "10%";
  if (categoryCount === 1) return "54%";
  if (categoryCount === 2) return "34%";
  if (categoryCount === 3) return "24%";
  if (categoryCount <= 5) return "17%";
  if (categoryCount <= 8) return "12%";
  if (categoryCount <= 12) return "8%";
  return "5%";
}

/**
 * 카테고리가 적을 때 막대가 차트 정중앙에만 떠 보이지 않도록 X축 픽셀 패딩(특히 right로 살짝 왼쪽 시선).
 */
export function defectPpmXAxisPaddingPx(categoryCount: number): { left: number; right: number } {
  if (categoryCount <= 0) return { left: 12, right: 28 };
  if (categoryCount === 1) return { left: 40, right: 320 };
  if (categoryCount === 2) return { left: 34, right: 240 };
  if (categoryCount === 3) return { left: 30, right: 180 };
  if (categoryCount <= 5) return { left: 26, right: 120 };
  if (categoryCount <= 8) return { left: 20, right: 72 };
  if (categoryCount <= 12) return { left: 16, right: 48 };
  return { left: 12, right: 32 };
}

/** 주차·월별 차트 막대 레이아웃 옵션(디버그·문서용 동일 기준) */
export function getDefectPpmBarLayoutOptions(categoryCount: number) {
  return {
    chartKind: "defect-ppm-composed" as const,
    fixedChartWidthPx: DEFECT_PPM_FIXED_CHART_WIDTH,
    plotHeightPx: DEFECT_PPM_PLOT_HEIGHT,
    margin: DEFECT_PPM_COMPOSED_CHART_MARGIN,
    barCategoryGap: defectPpmBarCategoryGap(categoryCount),
    xAxisPaddingPx: defectPpmXAxisPaddingPx(categoryCount),
    barMaxBarSize: null,
    barSize: null,
    barGap: null,
    categoryGap: null,
  };
}

export function buildWeeklyPdfLegendEntries(
  orderedDefectNames: readonly string[],
): readonly WeeklyPdfLegendEntry[] {
  const bars: WeeklyPdfLegendEntry[] = orderedDefectNames.map((label, i) => ({
    label,
    color: WEEKLY_DEFECT_STACK_COLORS[i % WEEKLY_DEFECT_STACK_COLORS.length],
    variant: "bar",
  }));
  return [
    ...bars,
    {
      label: "총 불량율(ppm)",
      color: WEEKLY_TOTAL_PPM_LINE_COLOR,
      variant: "line",
    },
  ];
}
