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
import {
  DEFECT_PPM_COMPOSED_CHART_MARGIN,
  DEFECT_PPM_FIXED_CHART_WIDTH,
  DEFECT_PPM_PLOT_HEIGHT,
  PDF_ONE_PAGE_CARD_BODY_CONTENT_WIDTH_PX,
  PDF_ONE_PAGE_INNER_PADDING_PX,
  PDF_ONE_PAGE_ROOT_WIDTH_PX,
  defectPpmBarCategoryGap,
  defectPpmPlotHeightForWidthPx,
  defectPpmXAxisPaddingPx,
} from "../weeklyDefectPpmShared";
import { PdfReportIconBadge } from "./PdfReportIconBadge";

const COLORS = [
  "#2563eb",
  "#16a34a",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
  "#f97316",
  "#84cc16",
];
const LOT_X_TICK = { fill: "#1e293b", fontSize: 12, fontWeight: 600 };
const LOT_Y_TICK = { fill: "#1e293b", fontSize: 12, fontWeight: 600 };
const LOT_AXIS_STROKE = "#64748b";
/** PDF 고정폭만: 세로 LOT ID 라벨(-90°)용 X축 밴드 높이만 96→104로 소폭 확대(막대·전체 차트 높이는 유지) */
const LOT_PDF_FIXED_X_AXIS_HEIGHT_PX = 104;

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
              backgroundColor: COLORS[idx % COLORS.length],
              borderRadius: 2,
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
      setRows(Array.isArray(res.lot_defects) ? res.lot_defects : []);
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

  const defectNames = useMemo(() => {
    const set = new Set<string>();
    rows
      .filter((r) => String(r.lot_id ?? "").trim().toUpperCase() !== "LOTID")
      .forEach((r) => {
      (r.defects ?? []).forEach((d) => {
        const n = String(d.name ?? "").trim();
        if (n) set.add(n);
      });
      });
    return [...set];
  }, [rows]);

  const chartData = useMemo(() => {
    return rows
      .filter((r) => String(r.lot_id ?? "").trim().toUpperCase() !== "LOTID")
      .map((r) => {
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
  }, [rows, defectNames]);

  const hasChart = chartData.length > 0 && defectNames.length > 0;

  /** 월별·주차별과 동일 좌우 여백; X축 LOT 라벨(세로)용으로 bottom만 크게 */
  const lotMargin = useMemo(
    () => ({ ...DEFECT_PPM_COMPOSED_CHART_MARGIN, bottom: 90 } as const),
    [],
  );
  const barCategoryGap = useMemo(() => defectPpmBarCategoryGap(chartData.length), [chartData.length]);
  const lotXAxisPadding = useMemo(() => defectPpmXAxisPaddingPx(chartData.length), [chartData.length]);

  /** PDF 1페이지 월별 카드 본문(차트) 가로·비율 높이 — `PDF_ONE_PAGE_CARD_BODY_CONTENT_WIDTH_PX` */
  const pdfOnePageChartW = PDF_ONE_PAGE_CARD_BODY_CONTENT_WIDTH_PX;
  const pdfOnePageChartH = defectPpmPlotHeightForWidthPx(pdfOnePageChartW);

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
    justifyContent: "center",
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
    return (
      <ComposedChart
        data={chartData}
        margin={marginOverride ?? lotMargin}
        barCategoryGap={barCategoryGap}
        {...(fixed && cw != null && ch != null ? { width: cw, height: ch } : {})}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
        <XAxis
          dataKey="lot_label"
          tick={LOT_X_TICK}
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
          tick={LOT_Y_TICK}
          tickLine={{ stroke: LOT_AXIS_STROKE }}
          axisLine={{ stroke: LOT_AXIS_STROKE }}
          tickFormatter={(v) => fmt(num(v))}
        />
        <Tooltip content={<LotTooltip />} />
        {defectNames.map((name, idx) => (
          <Bar key={name} dataKey={`d_${idx}`} stackId="stack" name={name} fill={COLORS[idx % COLORS.length]} />
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
            fontSize={11}
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
        pdfExportMode ? "pdf-export-mode" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ minWidth: 0, maxWidth: "100%", width: "100%", boxSizing: "border-box" }}
    >
      {!forceFixedChartSize ? (
        <h2 className="cardTitle">{PDF_CHART_SECTION_TITLE_LOT_PPM}</h2>
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
                <h2
                  className="cardTitle pdf-report-section-title pdf-one-page-chart-title"
                  style={{ display: "flex", alignItems: "center", gap: 10 }}
                >
                  <PdfReportIconBadge Icon={ChartColumn} title={PDF_CHART_SECTION_TITLE_LOT_PPM} />
                  <span className="pdf-report-section-title-text">{PDF_CHART_SECTION_TITLE_LOT_PPM}</span>
                </h2>
                <div style={lotPdfOnePageChartPlaceholderStyle}>
                  {hasChart ? (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "stretch",
                        width: "100%",
                        maxWidth: "100%",
                        alignSelf: "stretch",
                        backgroundColor: "#ffffff",
                        borderRadius: 4,
                      }}
                    >
                      {renderLotComposedChart(
                        true,
                        pdfOnePageChartW,
                        pdfOnePageChartH,
                        DEFECT_PPM_COMPOSED_CHART_MARGIN,
                      )}
                      <LotLegend labels={defectNames} wrapStyle={lotPdfOnePageLegendWrap} />
                    </div>
                  ) : (
                    <div className="hint" style={{ padding: 16, textAlign: "center", width: "100%" }}>
                      차트를 표시할 불량명이 없습니다.
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
                  <LotLegend labels={defectNames} />
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
