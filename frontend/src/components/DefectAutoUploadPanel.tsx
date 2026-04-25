import { useEffect, useState, type CSSProperties } from "react";
import {
  computeDefectAuto,
  getDefectAutoShipmentSummary,
  type DefectAutoShipmentSummary,
  uploadDefectShipment,
} from "../api";

type DefectAutoUploadPanelProps = {
  onComputeSuccess?: (weekly: unknown[], monthly: unknown[]) => void;
  workFile: File | null;
  /** 입력 카드에서 선택한 코드별 불량현황; compute 시 defect_file로 전송 */
  codeDefectFile: File | null;
};

/** 입력 카드 파일 행과 동일한 정렬·폭 감 */
const FILE_ROW: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  width: "100%",
  gap: 12,
};
const FILE_INPUT_WRAP: CSSProperties = {
  width: "68%",
  maxWidth: "28rem",
  minWidth: "9rem",
  flexShrink: 0,
};

/**
 * 공정불량 자동화: 출하 업로드, compute 시 부모에 weekly/monthly 전달(표 병합).
 * 작업일보·코드별 불량현황 파일은 입력 카드에서 선택합니다.
 */
export default function DefectAutoUploadPanel({
  onComputeSuccess,
  workFile,
  codeDefectFile,
}: DefectAutoUploadPanelProps) {
  const [shipmentFile, setShipmentFile] = useState<File | null>(null);
  const [defectAutoMessage, setDefectAutoMessage] = useState<string>("");
  const [defectAutoLoading, setDefectAutoLoading] = useState(false);
  const [shipmentSummary, setShipmentSummary] = useState<DefectAutoShipmentSummary | null>(null);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const res = await getDefectAutoShipmentSummary();
        if (mounted) setShipmentSummary(res.shipment_summary ?? null);
      } catch {
        if (mounted) setShipmentSummary(null);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  async function handleShipmentUpload() {
    if (!shipmentFile) {
      setDefectAutoMessage("출하 파일을 먼저 선택하세요.");
      return;
    }
    setDefectAutoLoading(true);
    setDefectAutoMessage("");
    try {
      const res = await uploadDefectShipment(shipmentFile);
      setShipmentSummary(res.shipment_summary ?? null);
      setDefectAutoMessage(res.message || "출하 저장 완료");
      window.alert(res.message || "출하 저장 완료");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setDefectAutoMessage(msg);
      window.alert(`실패: ${msg}`);
    } finally {
      setDefectAutoLoading(false);
    }
  }

  async function handleCompute() {
    if (!codeDefectFile) {
      setDefectAutoMessage("입력 카드에서 코드별 불량현황 엑셀을 먼저 선택해주세요.");
      return;
    }
    if (!workFile) {
      setDefectAutoMessage("입력 카드에서 작업일보 엑셀을 먼저 선택해주세요.");
      return;
    }
    setDefectAutoLoading(true);
    setDefectAutoMessage("");
    try {
      const res = await computeDefectAuto(codeDefectFile, workFile);
      console.log("[defect-auto] weekly", res.weekly);
      console.log("[defect-auto] monthly", res.monthly);
      onComputeSuccess?.(res.weekly, res.monthly);
      setDefectAutoMessage(
        "공정불량 자동 계산이 완료되었습니다. 주차별·월별 표에 병합 반영됩니다.",
      );
      window.alert("공정불량 자동 계산이 완료되었습니다. (주·월 표에 병합 반영)");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setDefectAutoMessage(msg);
      window.alert(`실패: ${msg}`);
    } finally {
      setDefectAutoLoading(false);
    }
  }

  return (
    <section className="card" data-pdf-exclude="meta">
      <h2 className="cardTitle">공정불량 자동화</h2>
      <p className="hint" style={{ marginBottom: 12 }}>
        출하 파일(공장 받기.xlsx)을 서버에 올린 뒤 자동 집계합니다. &quot;공정불량 자동 계산&quot; 성공 시
        같은
        주차·같은 월 행은 자동 집계로 덮어쓰고, 나머지 수기 행은 유지됩니다. 작업일보·코드별
        불량현황은 입력 카드에서 선택한 파일을 사용합니다. 저장은 각각 주차/월별 카드의 저장
        버튼을 사용하세요.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
        <div style={FILE_ROW}>
          <label
            htmlFor="defect-auto-shipment-file"
            className="label"
            style={{
              margin: 0,
              padding: 0,
              whiteSpace: "nowrap",
              flexShrink: 0,
              fontSize: 12,
            }}
          >
            출하 파일
          </label>
          <div style={FILE_INPUT_WRAP}>
            <input
              id="defect-auto-shipment-file"
              type="file"
              accept=".xlsx,.xls"
              disabled={defectAutoLoading}
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setShipmentFile(f);
                setDefectAutoMessage(f ? `선택됨: ${f.name}` : "");
              }}
              style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }}
            />
          </div>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
            marginTop: 8,
          }}
        >
          <button
            type="button"
            className="button"
            disabled={defectAutoLoading}
            onClick={handleShipmentUpload}
          >
            출하 파일 업로드
          </button>
          <button
            type="button"
            className="button"
            disabled={defectAutoLoading}
            onClick={handleCompute}
          >
            공정불량 자동 계산
          </button>
        </div>
      </div>

      <div className="hint" style={{ marginTop: 12, marginBottom: 0 }}>
        {shipmentSummary
          ? `출하 누적: ${shipmentSummary.min_date} ~ ${shipmentSummary.max_date} / Lot ${shipmentSummary.lot_count}건 / 이동수량 ${shipmentSummary.total_qty.toLocaleString("ko-KR")}`
          : "출하 누적: 아직 업로드된 출하 데이터가 없습니다."}
      </div>

      {defectAutoMessage ? (
        <div className="hint" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
          {defectAutoMessage}
        </div>
      ) : null}
      {defectAutoLoading ? <div className="hint">처리 중…</div> : null}
    </section>
  );
}
