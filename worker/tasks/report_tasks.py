import structlog
from tasks.celery_app import app

log = structlog.get_logger()


@app.task(name="tasks.report_tasks.generate_pdf_report")
def generate_pdf_report(report_id: str, inspection_id: str):
    """
    PDF 리포트 생성 태스크

    포함 내용:
    - 점검 요약 (일시, 드론 정보, 파일 수)
    - 심각도별 결과 집계 테이블
    - 균열별 수치 (폭/길이/면적/점수)
    - 이전 점검 대비 변화량 (defect_track_entries.change_vs_prev)
    - 어노테이션 이미지 썸네일
    """
    log.info("report_generation_started", report_id=report_id)
    # TODO Phase 1: WeasyPrint 기반 HTML→PDF 구현
    log.info("report_generation_completed", report_id=report_id)
    return {"status": "completed", "report_id": report_id}
