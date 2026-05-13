import React from "react";
import { getDefectColor } from "./defectNameColors";

/** SVG fragment id: ASCII만 사용, 길이 상한 */
export function defectPdfGradientId(prefix: string, index: number, defectName: string): string {
  const raw = `${prefix}_i${index}_${defectName}`;
  const safe = raw.replace(/[^a-zA-Z0-9_-]/g, "_");
  return safe.length > 120 ? safe.slice(0, 120) : safe;
}

function mixHexWithWhite(hex: string, amount: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim());
  if (!m) return String(hex);
  const n = parseInt(m[1], 16);
  let r = (n >> 16) & 255;
  let g = (n >> 8) & 255;
  let b = n & 255;
  r = Math.round(r + (255 - r) * amount);
  g = Math.round(g + (255 - g) * amount);
  b = Math.round(b + (255 - b) * amount);
  return `#${[r, g, b].map((x) => x.toString(16).padStart(2, "0")).join("")}`;
}

export function defectPdfBarFill(
  pdfMode: boolean,
  idPrefix: string,
  index: number,
  defectName: string,
  solidColor: string,
): string {
  if (!pdfMode) return solidColor;
  return `url(#${defectPdfGradientId(idPrefix, index, defectName)})`;
}

type DefectPdfBarGradientDefsProps = {
  enabled: boolean;
  idPrefix: string;
  defectNames: readonly string[];
  /** LOT 등 막대 많을 때 위쪽 밝기 비율 축소 */
  subtle?: boolean;
};

/** ComposedChart 내부 첫 children 근처 — PDF 캡처 시에만 렌더 */
export function DefectPdfBarGradientDefs({
  enabled,
  idPrefix,
  defectNames,
  subtle = false,
}: DefectPdfBarGradientDefsProps): React.ReactElement | null {
  if (!enabled) return null;
  /** PDF 막대 상단만 흰색 혼합 5~10%(대시보드는 solid 유지) */
  const topMix = subtle ? 0.05 : 0.08;
  return (
    <defs>
      {defectNames.map((name, idx) => {
        const base = getDefectColor(name);
        const top = mixHexWithWhite(base, topMix);
        const id = defectPdfGradientId(idPrefix, idx, name);
        return (
          <linearGradient key={`${idPrefix}-${idx}`} id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={top} />
            <stop offset="100%" stopColor={base} />
          </linearGradient>
        );
      })}
    </defs>
  );
}
