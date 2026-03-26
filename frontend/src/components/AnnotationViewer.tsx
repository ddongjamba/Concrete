"use client";
import { useEffect, useRef, useState } from "react";
import { cn, severityDotColor } from "@/lib/utils";

interface BBox { x: number; y: number; w: number; h: number; }
interface Result {
  id: string;
  defect_type: string;
  severity_score: number;
  confidence: number;
  crack_width_mm: number | null;
  bounding_box: BBox;
  annotated_image_url: string | null;
}

interface Props {
  results: Result[];
  selectedId: string | null;
  onSelect: (r: Result | null) => void;
  onDelete: (id: string) => void;
}

const SEVERITY_STROKE: Record<string, string> = {
  critical: "#dc2626",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
};

function strokeColor(score: number): string {
  if (score >= 80) return SEVERITY_STROKE.critical;
  if (score >= 60) return SEVERITY_STROKE.high;
  if (score >= 30) return SEVERITY_STROKE.medium;
  return SEVERITY_STROKE.low;
}

const DEFECT_KO: Record<string, string> = {
  crack: "균열", spalling: "박리", efflorescence: "백태",
  stain: "오염", delamination: "층간분리", other: "기타",
};

export default function AnnotationViewer({ results, selectedId, onSelect, onDelete }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [imgSize, setImgSize] = useState({ w: 0, h: 0 });
  const [scale, setScale] = useState(1);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [newBbox, setNewBbox] = useState<BBox | null>(null);

  // 플레이스홀더 이미지 (실제에서는 annotated_image_url 사용)
  const bgColor = "#1e293b";
  const canvasW = 960;
  const canvasH = 640;

  useEffect(() => {
    drawCanvas();
  }, [results, selectedId, newBbox]);

  const drawCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 배경 (실제에서는 이미지 그리기)
    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#334155";
    ctx.font = "16px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("드론 이미지 (실제 환경에서 표시)", canvas.width / 2, canvas.height / 2);

    // 각 결함 bbox 그리기
    results.forEach((r) => {
      const { x, y, w, h } = r.bounding_box;
      const px = x * canvas.width;
      const py = y * canvas.height;
      const pw = w * canvas.width;
      const ph = h * canvas.height;

      const selected = r.id === selectedId;
      const color = strokeColor(r.severity_score);

      // bbox 사각형
      ctx.strokeStyle = color;
      ctx.lineWidth = selected ? 3 : 2;
      ctx.setLineDash(selected ? [] : []);
      ctx.strokeRect(px - pw / 2, py - ph / 2, pw, ph);

      // 배경 채우기 (선택 시 강조)
      ctx.fillStyle = selected ? `${color}22` : `${color}11`;
      ctx.fillRect(px - pw / 2, py - ph / 2, pw, ph);

      // 라벨 배지
      const label = `${DEFECT_KO[r.defect_type] ?? r.defect_type} ${r.severity_score}`;
      ctx.font = "bold 11px sans-serif";
      const tw = ctx.measureText(label).width;
      const lx = px - pw / 2;
      const ly = py - ph / 2 - 18;

      ctx.fillStyle = color;
      ctx.fillRect(lx, ly, tw + 10, 16);
      ctx.fillStyle = "white";
      ctx.textAlign = "left";
      ctx.fillText(label, lx + 5, ly + 12);

      // 균열 폭 표시
      if (r.crack_width_mm) {
        ctx.font = "10px sans-serif";
        ctx.fillStyle = color;
        ctx.textAlign = "center";
        ctx.fillText(`${r.crack_width_mm.toFixed(1)}mm`, px, py + ph / 2 + 14);
      }
    });

    // 새로 그리는 bbox
    if (newBbox) {
      ctx.strokeStyle = "#60a5fa";
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]);
      ctx.strokeRect(
        newBbox.x * canvas.width,
        newBbox.y * canvas.height,
        newBbox.w * canvas.width,
        newBbox.h * canvas.height,
      );
      ctx.setLineDash([]);
    }
  };

  const canvasToNorm = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { nx: 0, ny: 0 };
    const rect = canvas.getBoundingClientRect();
    const nx = (clientX - rect.left) / rect.width;
    const ny = (clientY - rect.top) / rect.height;
    return { nx, ny };
  };

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { nx, ny } = canvasToNorm(e.clientX, e.clientY);

    // 클릭한 위치의 결함 찾기
    const hit = results.find((r) => {
      const { x, y, w, h } = r.bounding_box;
      return nx >= x - w / 2 && nx <= x + w / 2 && ny >= y - h / 2 && ny <= y + h / 2;
    });
    onSelect(hit ?? null);
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) return;
    const { nx, ny } = canvasToNorm(e.clientX, e.clientY);
    setDragStart({ x: nx, y: ny });
    setIsDragging(false);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!dragStart) return;
    const { nx, ny } = canvasToNorm(e.clientX, e.clientY);
    const dx = Math.abs(nx - dragStart.x);
    const dy = Math.abs(ny - dragStart.y);
    if (dx > 0.01 || dy > 0.01) {
      setIsDragging(true);
      setNewBbox({
        x: Math.min(dragStart.x, nx),
        y: Math.min(dragStart.y, ny),
        w: Math.abs(nx - dragStart.x),
        h: Math.abs(ny - dragStart.y),
      });
    }
  };

  const handleMouseUp = () => {
    if (isDragging && newBbox) {
      // 새 bbox 확정 → 실제에서는 API로 새 결함 추가
      console.log("New bbox:", newBbox);
    }
    setDragStart(null);
    setIsDragging(false);
    setNewBbox(null);
  };

  return (
    <div ref={containerRef} className="flex-1 flex flex-col overflow-hidden bg-slate-900">
      {/* 툴바 */}
      <div className="px-4 py-2 bg-slate-800 border-b border-slate-700 flex items-center gap-4">
        <span className="text-xs text-slate-400">
          클릭: 결함 선택 · 드래그: 새 bbox 추가
        </span>
        {selectedId && (
          <button
            onClick={() => { onDelete(selectedId); onSelect(null); }}
            className="ml-auto text-xs text-red-400 hover:text-red-300 border border-red-800 px-2.5 py-1 rounded hover:bg-red-900/30 transition-colors"
          >
            🗑 선택 삭제 (오탐지)
          </button>
        )}
      </div>

      {/* 캔버스 */}
      <div className="flex-1 flex items-center justify-center overflow-auto p-4">
        <canvas
          ref={canvasRef}
          width={canvasW}
          height={canvasH}
          className="max-w-full max-h-full rounded-lg cursor-crosshair"
          style={{ objectFit: "contain" }}
          onClick={isDragging ? undefined : handleCanvasClick}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        />
      </div>

      {/* 선택된 결함 상세 */}
      {selectedId && (() => {
        const r = results.find((x) => x.id === selectedId);
        if (!r) return null;
        return (
          <div className="px-4 py-3 bg-slate-800 border-t border-slate-700 flex items-center gap-6">
            <div className="flex items-center gap-2">
              <span className={cn("w-2.5 h-2.5 rounded-full", severityDotColor(r.severity_score))} />
              <span className="text-sm font-medium text-white">
                {DEFECT_KO[r.defect_type] ?? r.defect_type}
              </span>
            </div>
            <Stat label="심각도" value={r.severity_score.toString()} />
            <Stat label="신뢰도" value={`${(r.confidence * 100).toFixed(0)}%`} />
            {r.crack_width_mm && <Stat label="균열 폭" value={`${r.crack_width_mm.toFixed(1)}mm`} />}
          </div>
        );
      })()}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-xs">
      <span className="text-slate-400">{label}: </span>
      <span className="text-white font-medium">{value}</span>
    </div>
  );
}
