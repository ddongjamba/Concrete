"""
균열 악화 알림 서비스

트리거:
  - tracking_tasks.py 에서 track.status = 'worsening' 으로 변경될 때 호출
  - Celery 태스크 내부(동기 컨텍스트)에서도 사용할 수 있도록 동기 함수로 작성

알림 채널:
  1. 이메일 (SMTP) — 테넌트 admin/manager 전원에게 발송
  2. 앱 내 알림 (defect_alerts 테이블)
"""
import smtplib
import os
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

log = structlog.get_logger()

_SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASSWORD", "")
_EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@facade-inspect.com")
_EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"


def send_worsening_alert(
    *,
    recipients: list[str],
    project_name: str,
    location_zone: str | None,
    track_id: str,
    score_before: int,
    score_after: int,
    crack_width_mm: float | None,
    width_delta: float | None,
) -> None:
    """균열 악화 이메일 발송"""
    if not _EMAIL_ENABLED or not recipients:
        log.info("email_skipped", enabled=_EMAIL_ENABLED, recipients=len(recipients))
        return

    zone_label = location_zone or "위치 미지정"
    subject = f"[Facade Inspect] 균열 악화 경보 — {project_name} {zone_label}"

    width_info = ""
    if crack_width_mm:
        width_info = f"<br>현재 균열 폭: <strong>{crack_width_mm:.2f} mm</strong>"
        if width_delta:
            width_info += f" (이전 대비 +{width_delta:.2f} mm)"

    html = f"""
    <html><body style="font-family:sans-serif;line-height:1.6">
    <h2 style="color:#dc2626">⚠️ 균열 악화 경보</h2>
    <table style="border-collapse:collapse;width:100%">
      <tr><td style="padding:8px;border:1px solid #e5e7eb"><strong>프로젝트</strong></td>
          <td style="padding:8px;border:1px solid #e5e7eb">{project_name}</td></tr>
      <tr><td style="padding:8px;border:1px solid #e5e7eb"><strong>위치</strong></td>
          <td style="padding:8px;border:1px solid #e5e7eb">{zone_label}</td></tr>
      <tr><td style="padding:8px;border:1px solid #e5e7eb"><strong>심각도 변화</strong></td>
          <td style="padding:8px;border:1px solid #e5e7eb">
            {score_before} → <strong style="color:#dc2626">{score_after}</strong>
            (△{score_after - score_before:+d})
          </td></tr>
    </table>
    {width_info}
    <p style="margin-top:20px">
      <a href="http://localhost:3000/defect-tracks/{track_id}"
         style="background:#2563eb;color:white;padding:10px 20px;text-decoration:none;border-radius:4px">
        균열 상세 보기
      </a>
    </p>
    <hr style="margin-top:30px">
    <p style="color:#6b7280;font-size:12px">
      이 메일은 Facade Inspect에서 자동 발송됩니다.
      알림을 받고 싶지 않으시면 설정에서 변경하세요.
    </p>
    </body></html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = _EMAIL_FROM
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(_SMTP_USER, _SMTP_PASS)
            smtp.sendmail(_EMAIL_FROM, recipients, msg.as_string())

        log.info("worsening_email_sent", to=recipients, track_id=track_id)
    except Exception as e:
        log.error("worsening_email_failed", error=str(e), track_id=track_id)


def insert_in_app_alert(db_session, *, tenant_id: str, track_id: str, project_name: str,
                        location_zone: str | None, score_before: int, score_after: int) -> None:
    """
    defect_alerts 테이블에 앱 내 알림 삽입.
    db_session: SQLAlchemy 동기 Session (Celery 워커)
    """
    from sqlalchemy import text
    now = datetime.now(timezone.utc)
    import uuid

    db_session.execute(text("""
        INSERT INTO defect_alerts (
            id, tenant_id, track_id, alert_type, title, body,
            is_read, created_at
        ) VALUES (
            :id, :tenant_id, :track_id, 'worsening',
            :title, :body,
            false, :now
        )
    """), {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "track_id": track_id,
        "title": f"균열 악화 — {project_name} {location_zone or ''}".strip(),
        "body": f"심각도 점수 {score_before} → {score_after} (△{score_after - score_before:+d})",
        "now": now,
    })
