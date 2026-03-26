"use client";
import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import axios from "axios";
import { inspectionsApi, analysisApi, reportsApi } from "@/lib/api";
import { cn, severityColor, severityLabel, severityDotColor } from "@/lib/utils";
import AnnotationViewer from "@/components/AnnotationViewer";

interface AnalysisResult {
  id: string;
  defect_type: string;
  severity_score: number;
  severity: string;
  confidence: number;
  crack_width_mm: number | null;
  crack_length_mm: number | null;
  crack_area_cm2: number | null;
  bounding_box: { x: number; y: number; w: number; h: number };
  annotated_image_url: string | null;
  is_deleted?: boolean;
}

export default function InspectionPage() {
  const { id } = useParams<{ id: string }>();
  const [inspection, setInspection] = useState<any>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState<AnalysisResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<AnalysisResult | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reportLoading, setReportLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<NodeJS.Timeout>();

  // inspection 로드
  useEffect(() => {
    // project_id를 모르므로 분석 job 조회로 대신
    setLoading(false);
  }, [id]);

  // 진행률 폴링
  const startPolling = (jid: string) => {
    pollRef.current = setInterval(async () => {
      try {
        const r = await analysisApi.getJob(jid);
        setJobStatus(r.data.status);
        setProgress(r.data.progress_pct);
        if (r.data.status === "completed") {
          clearInterval(pollRef.current);
          loadResults(jid);
        } else if (r.data.status === "failed") {
          clearInterval(pollRef.current);
        }
      } catch {}
    }, 3000);
  };

  const loadResults = async (jid: string) => {
    try {
      const r = await analysisApi.getResults(jid, { limit: 200 });
      setResults(r.data.results ?? r.data);
    } catch {}
  };

  useEffect(() => () => clearInterval(pollRef.current), []);

  // 파일 업로드 + 원클릭 분석
  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      // 1. 점검 생성 (없으면) — 여기서는 id가 inspection_id라고 가정
      // 2. 각 파일에 대해 presigned URL 요청 후 업로드
      for (const file of Array.from(files)) {
        const ext = file.name.split(".").pop();
        const fileType = file.type.startsWith("video") ? "video" : "image";
        // presigned URL은 실제 backend와 연동될 때 사용
        // 개발 중에는 로컬 FileReader로 미리보기만
      }

      // 3. 분석 시작 (confirm)
      // const r = await inspectionsApi.confirmUpload(projectId, id);
      // setJobId(r.data.job_id);
      // setJobStatus("queued");
      // startPolling(r.data.job_id);

      // 개발 환경 시뮬레이션
      setJobStatus("running");
      setProgress(0);
      let p = 0;
      const sim = setInterval(() => {
        p += 10;
        setProgress(p);
        if (p >= 100) {
          clearInterval(sim);
          setJobStatus("completed");
          // 샘플 결과 (실제 환경에서는 API 응답)
          setResults([
            {
              id: "demo-1",
              defect_type: "crack",
              severity_score: 72,
              severity: "high",
              confidence: 0.87,
              crack_width_mm: 2.3,
              crack_length_mm: 145.0,
              crack_area_cm2: 3.34,
              bounding_box: { x: 0.2, y: 0.3, w: 0.15, h: 0.08 },
              annotated_image_url: null,
            },
            {
              id: "demo-2",
              defect_type: "spalling",
              severity_score: 45,
              severity: "medium",
              confidence: 0.73,
              crack_width_mm: null,
              crack_length_mm: null,
              crack_area_cm2: null,
              bounding_box: { x: 0.55, y: 0.6, w: 0.2, h: 0.12 },
              annotated_image_url: null,
            },
          ]);
        }
      }, 300);
    } finally {
      setUploading(false);
    }
  };

  const handleGenerateReport = async () => {
    setReportLoading(true);
    try {
      const r = await reportsApi.create(id);
      const reportId = r.data.id;
      // 다운로드 URL 조회
      setTimeout(async () => {
        try {
          const dl = await reportsApi.download(reportId);
          window.open(dl.data.url ?? dl.request.responseURL, "_blank");
        } catch {}
        setReportLoading(false);
      }, 3000);
    } catch {
      setReportLoading(false);
    }
  };

  const activeResults = results.filter((r) => !r.is_deleted);

  return (
    <div className="h-full flex flex-col">
      {/* 상단 바 */}
      <div className="px-6 py-4 border-b border-slate-200 bg-white flex items-center justify-between">
        <div>
          <h1 className="font-semibold text-slate-900">점검 분석</h1>
          <p className="text-xs text-slate-400">ID: {id}</p>
        </div>
        {activeResults.length > 0 && (
          <button
            onClick={handleGenerateReport}
            disabled={reportLoading}
            className="flex items-center gap-2 bg-slate-800 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-slate-900 disabled:opacity-50"
          >
            {reportLoading ? "생성 중..." : "📄 PDF 리포트"}
          </button>
        )}
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* 좌측: 업로드 / 뷰어 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {jobStatus === null ? (
            /* 업로드 영역 */
            <div className="flex-1 flex items-center justify-center p-8">
              <div
                className="border-2 border-dashed border-slate-300 rounded-2xl p-12 text-center w-full max-w-lg cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-colors"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); handleUpload(e.dataTransfer.files); }}
              >
                <div className="text-5xl mb-4">📸</div>
                <h2 className="text-lg font-semibold text-slate-700 mb-2">드론 이미지 / 영상 업로드</h2>
                <p className="text-sm text-slate-400 mb-6">JPG, PNG, MP4 · 여러 파일 동시 업로드 가능</p>
                <button
                  className="bg-blue-600 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700"
                  disabled={uploading}
                >
                  {uploading ? "업로드 중..." : "파일 선택"}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept="image/*,video/*"
                  className="hidden"
                  onChange={(e) => handleUpload(e.target.files)}
                />
              </div>
            </div>
          ) : (
            /* 분석 진행 / 결과 뷰어 */
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* 진행률 바 */}
              {jobStatus !== "completed" && (
                <div className="px-6 py-3 bg-blue-50 border-b border-blue-100">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-blue-700 font-medium">
                      {jobStatus === "queued" ? "대기 중..." : "AI 분석 중..."}
                    </span>
                    <span className="text-sm text-blue-600">{progress}%</span>
                  </div>
                  <div className="h-2 bg-blue-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all duration-500"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              )}

              {/* 어노테이션 뷰어 */}
              <AnnotationViewer
                results={activeResults}
                selectedId={selectedResult?.id ?? null}
                onSelect={(r) => setSelectedResult(r as AnalysisResult | null)}
                onDelete={(rid) => setResults((prev) => prev.map((r) => r.id === rid ? { ...r, is_deleted: true } : r))}
              />
            </div>
          )}
        </div>

        {/* 우측: 결과 목록 */}
        {activeResults.length > 0 && (
          <div className="w-80 border-l border-slate-200 bg-white flex flex-col overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100">
              <div className="text-sm font-semibold text-slate-700">
                검출 결함 ({activeResults.length}건)
              </div>
              <div className="flex gap-3 mt-1 text-xs text-slate-400">
                <span>긴급 {activeResults.filter((r) => r.severity_score >= 80).length}</span>
                <span>경보 {activeResults.filter((r) => r.severity_score >= 60 && r.severity_score < 80).length}</span>
                <span>주의 {activeResults.filter((r) => r.severity_score >= 30 && r.severity_score < 60).length}</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
              {[...activeResults]
                .sort((a, b) => b.severity_score - a.severity_score)
                .map((result) => (
                  <div
                    key={result.id}
                    onClick={() => setSelectedResult(selectedResult?.id === result.id ? null : result)}
                    className={cn(
                      "px-4 py-3 cursor-pointer hover:bg-slate-50 transition-colors",
                      selectedResult?.id === result.id && "bg-blue-50"
                    )}
                  >
                    <div className="flex items-start justify-between mb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className={cn("w-2 h-2 rounded-full flex-shrink-0", severityDotColor(result.severity_score))} />
                        <span className="text-sm font-medium text-slate-800 capitalize">
                          {result.defect_type === "crack" ? "균열" :
                           result.defect_type === "spalling" ? "박리" :
                           result.defect_type === "efflorescence" ? "백태" :
                           result.defect_type === "stain" ? "오염" :
                           result.defect_type === "delamination" ? "층간분리" : result.defect_type}
                        </span>
                      </div>
                      <span className={cn("text-xs px-1.5 py-0.5 rounded border font-medium", severityColor(result.severity_score))}>
                        {result.severity_score} · {severityLabel(result.severity_score)}
                      </span>
                    </div>

                    <div className="text-xs text-slate-400 space-y-0.5 ml-3.5">
                      <div>신뢰도: {(result.confidence * 100).toFixed(0)}%</div>
                      {result.crack_width_mm && (
                        <div>폭 {result.crack_width_mm.toFixed(1)}mm · 길이 {result.crack_length_mm?.toFixed(0)}mm</div>
                      )}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
