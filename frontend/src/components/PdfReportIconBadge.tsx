import type { LucideIcon } from "lucide-react";

/** PDF(html2canvas) 캡처 시 섹션 제목 옆에만 쓰는 SVG 픽토그램 배지 (이모지 미사용) */
export function PdfReportIconBadge({
  Icon,
  title,
}: {
  Icon: LucideIcon;
  /** 네이티브 툴팁(장식용 배지) */
  title?: string;
}) {
  return (
    <span className="pdf-report-icon-badge" aria-hidden title={title}>
      <Icon size={15} strokeWidth={2.25} />
    </span>
  );
}
