"""
PDF 리포트 생성 서비스.

포함 내용:
- 점검 요약 (건물명, 날짜, 드론 모델, 파일 수)
- 심각도별 결과 집계 테이블
- 균열별 상세 수치 (폭/길이/면적/점수)
- 이전 점검 대비 변화량 (defect_track_entries.change_vs_prev)
- 어노테이션 이미지 (심각도 높은 순 상위 20개)
"""
import os
import tempfile
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.analysis import AnalysisResult, AnalysisJob, SeverityLevel
from app.models.inspection import Inspection
from app.models.project import Project
from app.services.storage_service import StorageService


SEVERITY_KO = {
    "low": "관찰",
    "medium": "주의",
    "high": "경보",
    "critical": "긴급",
}
SEVERITY_COLOR = {
    "low": "#22c55e",
    "medium": "#f59e0b",
    "high": "#ef4444",
    "critical": "#7f1d1d",
}


def _build_html(
    project: Project,
    inspection: Inspection,
    results: list[AnalysisResult],
    image_urls: dict[str, str],  # result.id → presigned URL
) -> str:
    # 집계
    counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for r in results:
        counts[r.severity.value] += 1

    rows_html = ""
    for i, r in enumerate(results, 1):
        img_tag = ""
        if r.id in image_urls:
            img_tag = f'<img src="{image_urls[r.id]}" style="max-width:200px;border-radius:4px;">'
        color = SEVERITY_COLOR[r.severity.value]
        sev_ko = SEVERITY_KO[r.severity.value]

        width_str = f"{float(r.crack_width_mm):.1f} mm" if r.crack_width_mm else "—"
        length_str = f"{float(r.crack_length_mm):.1f} mm" if r.crack_length_mm else "—"
        area_str = f"{float(r.crack_area_cm2):.2f} cm²" if r.crack_area_cm2 else "—"

        rows_html += f"""
        <tr>
          <td>{i}</td>
          <td>{r.defect_type.value}</td>
          <td style="color:{color};font-weight:bold">{sev_ko} ({r.severity_score}점)</td>
          <td>{float(r.confidence)*100:.0f}%</td>
          <td>{width_str}</td>
          <td>{length_str}</td>
          <td>{area_str}</td>
          <td>{img_tag}</td>
        </tr>"""

    summary_html = "".join(
        f'<span style="color:{SEVERITY_COLOR[k]};margin-right:16px;font-size:1.1em">'
        f'<b>{SEVERITY_KO[k]}</b>: {v}건</span>'
        for k, v in counts.items()
    )

    report_date = datetime.now(timezone.utc).strftime("%Y년 %m월 %d일")
    insp_date = inspection.inspection_date.strftime("%Y년 %m월 %d일") if inspection.inspection_date else "—"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Noto Sans KR', sans-serif; margin: 40px; color: #1f2937; }}
  h1 {{ color: #1e40af; font-size: 1.8em; border-bottom: 3px solid #1e40af; padding-bottom: 8px; }}
  h2 {{ color: #374151; font-size: 1.2em; margin-top: 32px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.9em; }}
  th {{ background: #1e40af; color: white; padding: 8px; text-align: left; }}
  td {{ padding: 8px; border-bottom: 1px solid #e5e7eb; vertical-align: middle; }}
  tr:nth-child(even) {{ background: #f9fafb; }}
  .meta {{ background: #f3f4f6; padding: 16px; border-radius: 8px; margin-bottom: 24px; }}
  .meta td {{ border: none; padding: 4px 12px; }}
  .summary {{ margin: 16px 0; padding: 12px; background: #fefce8; border-radius: 8px; }}
</style>
</head>
<body>
<h1>외벽 균열 점검 보고서</h1>

<div class="meta">
  <table>
    <tr><td><b>건물명</b></td><td>{project.name}</td><td><b>주소</b></td><td>{project.address or '—'}</td></tr>
    <tr><td><b>점검명</b></td><td>{inspection.label or '—'}</td><td><b>점검일</b></td><td>{insp_date}</td></tr>
    <tr><td><b>드론 모델</b></td><td>{inspection.drone_model or '—'}</td><td><b>비행 고도</b></td><td>{inspection.flight_altitude_m or '—'} m</td></tr>
    <tr><td><b>분석 이미지 수</b></td><td>{inspection.file_count}장</td><td><b>보고서 생성일</b></td><td>{report_date}</td></tr>
  </table>
</div>

<h2>분석 결과 요약</h2>
<div class="summary">{summary_html}</div>
<p>총 <b>{len(results)}건</b>의 결함이 탐지되었습니다.</p>

<h2>균열 상세 목록 (심각도 높은 순)</h2>
<table>
  <thead>
    <tr>
      <th>#</th><th>결함 유형</th><th>심각도</th><th>신뢰도</th>
      <th>균열 폭</th><th>균열 길이</th><th>면적</th><th>이미지</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>

<p style="margin-top:40px;color:#9ca3af;font-size:0.8em">
  본 보고서는 AI 자동 분석 결과이며, 최종 판단은 전문가의 현장 확인이 필요합니다.
  Facade Inspect — https://github.com/ddongjamba/Concrete
</p>
</body>
</html>"""


async def generate_report(
    inspection_id: str,
    report_id: str,
    db: AsyncSession,
) -> str:
    """
    HTML → PDF 변환 후 S3 저장. 저장된 storage_key 반환.
    WeasyPrint 사용 (한글 폰트: Noto Sans KR CDN).
    """
    from weasyprint import HTML

    # 데이터 조회
    result = await db.execute(
        select(Inspection).where(Inspection.id == uuid.UUID(inspection_id))
    )
    inspection = result.scalar_one_or_none()
    if not inspection:
        raise ValueError("점검을 찾을 수 없습니다")

    proj_result = await db.execute(
        select(Project).where(Project.id == inspection.project_id)
    )
    project = proj_result.scalar_one_or_none()

    # 최신 완료된 job의 결과 조회 (심각도 높은 순)
    job_result = await db.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.inspection_id == inspection.id,
            AnalysisJob.status == "completed",
        )
        .order_by(AnalysisJob.created_at.desc())
        .limit(1)
    )
    job = job_result.scalar_one_or_none()

    results = []
    image_urls = {}
    if job:
        res_result = await db.execute(
            select(AnalysisResult)
            .where(AnalysisResult.job_id == job.id)
            .order_by(AnalysisResult.severity_score.desc())
            .limit(100)
        )
        results = res_result.scalars().all()

        # 상위 20개만 이미지 URL 생성
        storage = StorageService()
        for r in results[:20]:
            if r.annotated_image_key:
                image_urls[r.id] = await storage.generate_presigned_get(r.annotated_image_key)

    html_content = _build_html(project, inspection, results, image_urls)

    # PDF 생성
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    HTML(string=html_content).write_pdf(tmp_path)

    # S3 업로드
    storage_key = f"{inspection.tenant_id}/reports/{report_id}.pdf"
    storage = StorageService()
    upload_fn = storage.client.upload_file
    upload_fn(tmp_path, storage.bucket, storage_key, ExtraArgs={"ContentType": "application/pdf"})
    os.unlink(tmp_path)

    return storage_key
