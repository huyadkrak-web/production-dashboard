import React, { useEffect, useMemo, useState } from "react";
import { ChartColumn } from "lucide-react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { type DefectAutoLotDefectRow, getDefectAutoLotDefects } from "../api";
import { PDF_CHART_SECTION_TITLE_LOT_PPM } from "../pdfChartSectionTitles";
import { getDefectColor } from "../defectNameColors";
import { DefectPdfBarGradientDefs, defectPdfBarFill } from "../defectPdfBarGradients";
import {
  DEFECT_PPM_COMPOSED_CHART_MARGIN,
  DEFECT_PPM_FIXED_CHART_WIDTH,
  DEFECT_PPM_PLOT_HEIGHT,
  PDF_ONE_PAGE_CARD_BODY_CONTENT_WIDTH_PX,
  PDF_ONE_PAGE_INNER_PADDING_PX,
  PDF_ONE_PAGE_ROOT_WIDTH_PX,
  defectPpmBarCategoryGap,
  defectPpmXAxisPaddingPx,
} from "../weeklyDefectPpmShared";
import { PdfReportIconBadge } from "./PdfReportIconBadge";
/** LOT별 그래프·PDF에 표시할 최대 LOT 수(저장/API 데이터는 그대로, 화면만 제한) */
const LOT_CHART_VISIBLE_LIMIT = 50;
const LOT_CHART_VISIBLE_HINT_LABEL = "최근 50 LOT 기준";

const lotChartVisibleHintStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 500,
  color: "var(--muted, #64748b)",
  lineHeight: 1.3,
  whiteSpace: "nowrap",
  flexShrink: 0,
};

const LOT_X_TICK = { fill: "#1e293b", fontSize: 12, fontWeight: 600 };
const LOT_Y_TICK = { fill: "#1e293b", fontSize: 12, fontWeight: 600 };
const LOT_AXIS_STROKE = "#64748b";
/** PDF 고정폭: 세로 LOT ID 라벨(-90°)용 X축 밴드 높이(대시보드 96px에 맞춤) */
const LOT_PDF_FIXED_X_AXIS_HEIGHT_PX = 96;
/** LOT PDF: 1페이지 카드 본문 가로 전체(주·월 `DEFECT_PPM_FIXED_CHART_WIDTH`보다 넓음) — LOT 라벨·ppm 라벨 겹침 완화 */
const LOT_PDF_CHART_WIDTH_PX = PDF_ONE_PAGE_CARD_BODY_CONTENT_WIDTH_PX;

type LotDefectPpmProps = {
  forceFixedChartSize?: boolean;
  pdfExportMode?: boolean;
  /** 공정불량 자동계산 성공 토큰이 바뀌면 LOT 집계를 자동 새로고침 */
  autoReloadToken?: number | null;
};

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function fmt(v: number): string {
  if (!Number.isFinite(v)) return "";
  return Math.round(v).toLocaleString("ko-KR");
}

function shortenLotId(id: string): string {
  const t = String(id ?? "");
  if (t.length <= 14) return t;
  return `${t.slice(0, 6)}...${t.slice(-4)}`;
}

function isValidLotRow(r: DefectAutoLotDefectRow): boolean {
  return String(r.lot_id ?? "").trim().toUpperCase() !== "LOTID";
}

/** 출하 move_date(YYYY-MM-DD) 정렬 키 — 파싱 실패 시 0(앞쪽) */
function moveDateSortKey(moveDate: string): number {
  const s = String(moveDate ?? "").trim().slice(0, 10);
  const t = Date.parse(`${s}T00:00:00`);
  return Number.isFinite(t) ? t : 0;
}

/** move_date 오름차순 → 동일 날짜는 API 순서 유지 → 최신 N개만 */
function lotRowsForChartDisplay(
  rows: readonly DefectAutoLotDefectRow[],
  limit: number = LOT_CHART_VISIBLE_LIMIT,
): DefectAutoLotDefectRow[] {
  const valid = rows.filter(isValidLotRow);
  const indexed = valid.map((r, apiIndex) => ({ r, apiIndex }));
  indexed.sort((a, b) => {
    const d = moveDateSortKey(a.r.move_date ?? "") - moveDateSortKey(b.r.move_date ?? "");
    if (d !== 0) return d;
    return a.apiIndex - b.apiIndex;
  });
  const sorted = indexed.map((x) => x.r);
  const visible =
    sorted.length > limit ? sorted.slice(-limit) : sorted;
  const dropped = Math.max(0, valid.length - visible.length);
  console.log(
    "[lot_chart_visible_limit]",
    JSON.stringify({
      total_rows: valid.length,
      visible_rows: visible.length,
      limit,
      dropped_rows: dropped,
    }),
  );
  return visible;
}

type TooltipPayload = {
  dataKey?: string | number;
  value?: number;
  payload?: Record<string, unknown>;
  name?: string;
  color?: string;
};

function LotTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<TooltipPayload>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload ?? {};
  const defects = (row.defects as Array<Record<string, unknown>> | undefined) ?? [];
  return (
    <div
      className="card"
      style={{
        padding: "10px 12px",
        minWidth: 260,
        fontSize: 12,
        backgroundColor: "#ffffff",
        border: "1px solid #ddd",
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 6 }}>LOT: {String(row.lot_id ?? "")}</div>
      <div>출하일: {String(row.move_date ?? "")}</div>
      <div>출하수량: {fmt(num(row.move_qty))}</div>
      <div>총 불량수량: {fmt(num(row.defect_total))}</div>
      <div style={{ marginBottom: 6 }}>총 ppm: {fmt(num(row.total_ppm))}</div>
      {defects.length > 0 ? (
        defects.map((d, i) => (
          <div key={`${String(d.name ?? "")}-${i}`}>
            {String(d.name ?? "")}: count {fmt(num(d.count))}, ppm {fmt(num(d.ppm))}
          </div>
        ))
      ) : (
        <div>불량 없음</div>
      )}
    </div>
  );
}

function LotChartVisibleHint() {
  return <span className="hint" style={lotChartVisibleHintStyle}>{LOT_CHART_VISIBLE_HINT_LABEL}</span>;
}

function LotLegend({
  labels,
  wrapStyle,
}: {
  labels: string[];
  /** PDF 1페이지 `PDF_ONE_PAGE_MANUAL_LEGEND_WRAP`과 동일하게 맞출 때 전달 */
  wrapStyle?: React.CSSProperties;
}) {
  return (
    <div
      className="weekly-defect-manual-legend"
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        alignItems: "center",
        gap: "8px 16px",
        padding: "10px 12px 8px",
        fontSize: 12,
        fontWeight: 600,
        color: "#0f172a",
        lineHeight: 1.35,
        borderTop: "1px solid #e2e8f0",
        background: "#ffffff",
        boxSizing: "border-box",
        width: "100%",
        maxWidth: "100%",
        ...wrapStyle,
      }}
    >
      {labels.map((lab, idx) => (
        <span key={`${lab}-${idx}`} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              width: 14,
              height: 14,
              flexShrink: 0,
              backgroundColor: getDefectColor(lab),
              border: "1px solid #cbd5e1",
              borderRadius: 2,
              boxSizing: "border-box",
            }}
            aria-hidden
          />
          {lab}
        </span>
      ))}
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>총 ppm 라벨</span>
    </div>
  );
}

const LotDefectPpm = React.forwardRef<HTMLDivElement, LotDefectPpmProps>((props, ref) => {
  const { pdfExportMode = false, forceFixedChartSize = false, autoReloadToken = null } = props;
  const [rows, setRows] = useState<DefectAutoLotDefectRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const res = await getDefectAutoLotDefects();
      console.log("[lot_defects_api_raw]", res);
      const raw = res as unknown;
      const parsed = Array.isArray((raw as { lot_defects?: unknown }).lot_defects)
        ? ((raw as { lot_defects: DefectAutoLotDefectRow[] }).lot_defects ?? [])
        : Array.isArray(raw)
          ? (raw as DefectAutoLotDefectRow[])
          : [];
      console.log("[lot_defects_parsed_count]", parsed.length);
      setRows(parsed);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
    }
  }

  useEffect(() => {
    /* 대시보드 기본 화면은 수동 불러오기 기준. PDF 캡처 고정 모드에서만 필요 시 자동 로드 */
    if (!forceFixedChartSize) return;
    if (rows.length > 0 || error) return;
    void load();
  }, [forceFixedChartSize, rows.length, error]);

  useEffect(() => {
    if (autoReloadToken == null) return;
    void load();
  }, [autoReloadToken]);

  const visibleRows = useMemo(() => lotRowsForChartDisplay(rows), [rows]);

  const defectNames = useMemo(() => {
    const set = new Set<string>();
    visibleRows.forEach((r) => {
      (r.defects ?? []).forEach((d) => {
        const n = String(d.name ?? "").trim();
        if (n) set.add(n);
      });
    });
    return [...set];
  }, [visibleRows]);

  const chartData = useMemo(() => {
    return visibleRows.map((r) => {
      const base: Record<string, unknown> = {
        lot_id: String(r.lot_id ?? ""),
        lot_label: shortenLotId(String(r.lot_id ?? "")),
        move_date: String(r.move_date ?? ""),
        move_qty: num(r.move_qty),
        defect_total: num(r.defect_total),
        total_ppm: num(r.total_ppm),
        defects: (r.defects ?? []).map((d) => ({
          name: String(d.name ?? ""),
          count: num(d.count),
          ppm: num(d.ppm),
        })),
      };
      const map = new Map<string, number>();
      (r.defects ?? []).forEach((d) => {
        map.set(String(d.name ?? ""), num(d.ppm));
      });
      defectNames.forEach((name, idx) => {
        base[`d_${idx}`] = map.get(name) ?? 0;
      });
      return base;
    });
  }, [visibleRows, defectNames]);

  useEffect(() => {
    console.log("[lot_chart_data_count]", chartData.length);
    console.log("[lot_chart_first_row]", chartData.length > 0 ? chartData[0] : null);
  }, [chartData]);

  const hasChart = chartData.length > 0;

  /** PDF 캡처용 클래스(`styles.css`)만 구분. Y축·막대는 대시보드와 동일 linear 스택. */
  const pdfExportSurface = pdfExportMode || forceFixedChartSize;

  /** 월별·주차별과 동일 좌우 여백; X축 LOT 라벨(세로)용으로 bottom만 크게 */
  const lotMargin = useMemo(
    () => ({ ...DEFECT_PPM_COMPOSED_CHART_MARGIN, bottom: 90 } as const),
    [],
  );
  const barCategoryGap = useMemo(() => defectPpmBarCategoryGap(chartData.length), [chartData.length]);
  const lotXAxisPadding = useMemo(() => defectPpmXAxisPaddingPx(chartData.length), [chartData.length]);

  /** PDF 1페이지 월별 카드 본문(차트) 가로·비율 높이 — `PDF_ONE_PAGE_CARD_BODY_CONTENT_WIDTH_PX` */
  /** App.tsx `PDF_ONE_PAGE_CHART_PLACEHOLDER_STYLE` — 월별 1페이지 차트 영역과 동일 */
  const lotPdfOnePageChartPlaceholderStyle: React.CSSProperties = {
    width: "100%",
    minWidth: 0,
    minHeight: 220,
    marginTop: 8,
    border: "1px dashed #cbd5e1",
    borderRadius: 4,
    backgroundColor: "#f8fafc",
    display: "flex",
    alignItems: "stretch",
    justifyContent: "flex-start",
    color: "#64748b",
    fontSize: 13,
    boxSizing: "border-box",
  };

  /** App.tsx `PDF_ONE_PAGE_CARD_SECTION_STYLE` */
  const lotPdfOnePageCardSectionStyle: React.CSSProperties = {
    marginTop: 12,
    width: "100%",
    minWidth: 0,
    maxWidth: "none",
    boxSizing: "border-box",
  };

  /** App.tsx `PDF_ONE_PAGE_MANUAL_LEGEND_WRAP` */
  const lotPdfOnePageLegendWrap: React.CSSProperties = {
    padding: "10px 10px 8px",
    marginTop: 4,
  };

  function renderLotComposedChart(
    fixed: boolean,
    chartWidth?: number,
    chartHeight?: number,
    /** PDF 1페이지 월별 차트와 동일 플롯 비율을 맞출 때만 전달(일반 LOT는 세로 LOT 라벨용 `lotMargin`) */
    marginOverride?: typeof DEFECT_PPM_COMPOSED_CHART_MARGIN,
  ) {
    const cw = fixed ? (chartWidth ?? DEFECT_PPM_FIXED_CHART_WIDTH) : undefined;
    const ch = fixed ? (chartHeight ?? DEFECT_PPM_PLOT_HEIGHT) : undefined;
    const xDataKey = "lot_label";
    const xTick = LOT_X_TICK;
    const yTick = LOT_Y_TICK;
    const ppmTopLabelFs = 11;
    const usePdfBarStyle = Boolean(pdfExportSurface && fixed);

    return (
      <ComposedChart
        data={chartData}
        margin={marginOverride ?? lotMargin}
        barCategoryGap={barCategoryGap}
        {...(fixed && cw != null && ch != null ? { width: cw, height: ch } : {})}
      >
        <DefectPdfBarGradientDefs
          enabled={usePdfBarStyle}
          idPrefix="lotPdf"
          defectNames={defectNames}
          subtle
        />
        <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
        <XAxis
          dataKey={xDataKey}
          tick={xTick}
          tickLine={{ stroke: LOT_AXIS_STROKE }}
          axisLine={{ stroke: LOT_AXIS_STROKE }}
          angle={-90}
          textAnchor="end"
          tickMargin={10}
          height={fixed ? LOT_PDF_FIXED_X_AXIS_HEIGHT_PX : 96}
          interval={0}
          padding={lotXAxisPadding}
        />
        <YAxis
          tick={yTick}
          tickLine={{ stroke: LOT_AXIS_STROKE }}
          axisLine={{ stroke: LOT_AXIS_STROKE }}
          domain={[0, "auto"]}
          allowDecimals={false}
          tickFormatter={(v: number) => fmt(num(v))}
        />
        <Tooltip content={<LotTooltip />} />
        {defectNames.map((name, idx) => (
          <Bar
            key={name}
            dataKey={`d_${idx}`}
            stackId="stack"
            name={name}
            fill={defectPdfBarFill(usePdfBarStyle, "lotPdf", idx, name, getDefectColor(name))}
            isAnimationActive={!fixed}
          />
        ))}
        <Line
          dataKey="total_ppm"
          stroke="transparent"
          dot={false}
          activeDot={false}
          isAnimationActive={false}
        >
          <LabelList
            dataKey="total_ppm"
            position="top"
            fill="#6b7280"
            fontSize={ppmTopLabelFs}
            fontWeight={600}
            formatter={(v: unknown) => {
              const n = Number(v);
              if (!Number.isFinite(n)) return "";
              return Math.round(n).toLocaleString("ko-KR");
            }}
          />
        </Line>
      </ComposedChart>
    );
  }

  return (
    <section
      ref={ref}
      className={[
        forceFixedChartSize ? "" : "card",
        pdfExportSurface ? "pdf-export-mode" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ minWidth: 0, maxWidth: "100%", width: "100%", boxSizing: "border-box" }}
    >
      {!forceFixedChartSize ? (
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
            width: "100%",
          }}
        >
          <h2 className="cardTitle" style={{ marginBottom: 0 }}>
            {PDF_CHART_SECTION_TITLE_LOT_PPM}
          </h2>
          {hasChart ? <LotChartVisibleHint /> : null}
        </div>
      ) : null}
      {!forceFixedChartSize ? (
        <div
          className="actions"
          style={{ marginBottom: 8, display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 8 }}
        >
          <button type="button" className="button" onClick={() => void load()}>
            불러오기
          </button>
        </div>
      ) : null}
      {error ? (
        <div className="hint" style={{ color: "var(--danger)", marginBottom: 8 }}>
          {error}
        </div>
      ) : null}
      {chartData.length === 0 ? (
        <div className="hint">LOT별 집계 데이터가 없습니다. 공정불량 자동 계산 후 확인하세요.</div>
      ) : (
        <>
          {forceFixedChartSize ? (
            <div
              data-pdf-lot-card="true"
              style={{
                width: PDF_ONE_PAGE_ROOT_WIDTH_PX,
                minWidth: PDF_ONE_PAGE_ROOT_WIDTH_PX,
                maxWidth: PDF_ONE_PAGE_ROOT_WIDTH_PX,
                padding: PDF_ONE_PAGE_INNER_PADDING_PX,
                boxSizing: "border-box",
                backgroundColor: "#ffffff",
                overflow: "visible",
                marginLeft: "auto",
                marginRight: "auto",
              }}
            >
              <section
                className="card"
                style={{
                  width: "100%",
                  boxSizing: "border-box",
                  ...lotPdfOnePageCardSectionStyle,
                  marginTop: 0,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 12,
                    flexWrap: "wrap",
                    width: "100%",
                  }}
                >
                  <h2
                    className="cardTitle pdf-report-section-title pdf-one-page-chart-title"
                    style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 0, flex: "1 1 auto" }}
                  >
                    <PdfReportIconBadge Icon={ChartColumn} title={PDF_CHART_SECTION_TITLE_LOT_PPM} />
                    <span className="pdf-report-section-title-text">{PDF_CHART_SECTION_TITLE_LOT_PPM}</span>
                  </h2>
                  {hasChart ? <LotChartVisibleHint /> : null}
                </div>
                <div style={lotPdfOnePageChartPlaceholderStyle}>
                  {hasChart ? (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "stretch",
                        width: "100%",
                        maxWidth: "100%",
                        minWidth: 0,
                        alignSelf: "stretch",
                        backgroundColor: "#ffffff",
                        borderRadius: 4,
                      }}
                    >
                      <div
                        className={
                          pdfExportSurface && forceFixedChartSize
                            ? "weekly-defect-ppm-chart lot-defect-ppm-pdf-chart-surface"
                            : undefined
                        }
                        style={{
                          width: "100%",
                          maxWidth: "100%",
                          minWidth: 0,
                          flexShrink: 0,
                          display: "flex",
                          justifyContent: "flex-start",
                        }}
                      >
                        {renderLotComposedChart(
                          true,
                          LOT_PDF_CHART_WIDTH_PX,
                          DEFECT_PPM_PLOT_HEIGHT,
                          DEFECT_PPM_COMPOSED_CHART_MARGIN,
                        )}
                      </div>
                      {defectNames.length > 0 ? (
                        <LotLegend labels={defectNames} wrapStyle={lotPdfOnePageLegendWrap} />
                      ) : null}
                    </div>
                  ) : (
                    <div className="hint" style={{ padding: 16, textAlign: "center", width: "100%" }}>
                      차트를 표시할 데이터가 없습니다.
                    </div>
                  )}
                </div>
              </section>
            </div>
          ) : (
            <div
              className="weekly-defect-chart-capture-target"
              style={{
                background: "#ffffff",
                overflow: "visible",
                minHeight: 120,
                paddingTop: 8,
                width: "100%",
                maxWidth: "100%",
                minWidth: 0,
              }}
            >
              {hasChart ? (
                <div
                  className="weekly-defect-ppm-chart"
                  style={{
                    width: "100%",
                    minHeight: 520,
                    marginTop: 12,
                    boxSizing: "border-box",
                    maxWidth: "100%",
                    minWidth: 0,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "stretch",
                      width: "100%",
                      maxWidth: "100%",
                      overflowX: "auto",
                    }}
                  >
                    <ResponsiveContainer width="100%" height={DEFECT_PPM_PLOT_HEIGHT}>
                      {renderLotComposedChart(false)}
                    </ResponsiveContainer>
                  </div>
                  {defectNames.length > 0 ? <LotLegend labels={defectNames} /> : null}
                </div>
              ) : null}
            </div>
          )}
        </>
      )}
    </section>
  );
});

LotDefectPpm.displayName = "LotDefectPpm";
export default LotDefectPpm;
