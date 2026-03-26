# CLAUDE.md — Facade Inspect

드론 외벽 균열 탐지 프로젝트 가이드.

## 사업 모델

### 1단계: 용역 모델 (현재)
점검 업체가 드론 사진 전달 → 내부에서 Python AI 실행 + 오탐지 수동 수정 → 결과/보고서 납품.
수익보다 **실제 현장 데이터 확보 + 보고서 양식/불편점 파악**이 핵심 목적.

### 2단계: B2B SaaS (목표)
점검 업체에 유료 계정 발급 → 사진 직접 업로드 → AI 자동 분석 →
업체 직원이 **오탐지를 마우스로 수정** → 보고서/도면 다운로드.
월 구독료 또는 용량 과금. 서버만 유지하면 되는 구조.

**배포 방식 (미결정):**
- 웹 서비스 (현재 구현 방향): 브라우저 기반, 계정 관리 용이
- 데스크톱 실행파일 (검토 중): C++/Qt, 인터넷 불안정 환경 대응

## 프로젝트 위치
`/home/jimmy/Developer/SideProject/facade-inspect/`
GitHub: https://github.com/ddongjamba/Concrete

## 빌드 & 실행

```bash
cp .env.example .env
docker-compose up
```

| 서비스 | URL |
|--------|-----|
| 프론트엔드 | http://localhost:3000 |
| 백엔드 API | http://localhost:8000 |
| API 문서 | http://localhost:8000/docs |
| MinIO 콘솔 | http://localhost:9001 |
| Prometheus 메트릭 | http://localhost:8000/metrics |

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| AI 추론 | Python + PyTorch + YOLOv8 + SegFormer |
| 백엔드 | FastAPI + SQLAlchemy(async) + Alembic |
| 비동기 | Celery + Redis (큐: analysis / reports / tracking) |
| 스토리지 | MinIO (로컬) / AWS S3 (프로덕션) |
| 프론트엔드 | Next.js 14 App Router + Tailwind CSS + Recharts |
| DB | PostgreSQL 16 |
| 결제 | Stripe |
| 모니터링 | structlog (JSON) + Prometheus + DLQ (Redis) |

## 아키텍처 요약

```
드론 이미지/영상
    │ 업로드 (presigned S3 URL)
    ▼
FastAPI 백엔드 → Celery 태스크 enqueue
    │
    ▼
Celery 워커 — analysis 큐
    ├─ YOLOv8 배치 추론 → bbox + confidence
    ├─ SegFormer 픽셀 마스크 → 균열 면적 정밀 측정
    ├─ GSD 계산 → 균열 폭/길이/면적(mm/cm²) 환산
    ├─ severity_score 0-100 계산
    └─ 어노테이션 + 마스크 이미지 → S3 저장
    │
    ▼
Celery 워커 — tracking 큐
    ├─ GPS/IoU 기반 균열 매칭 → defect_tracks / defect_track_entries
    ├─ score_delta > 15 → status='worsening'
    └─ 악화 알림 (이메일 + 앱 내)
    │
    ▼
Next.js 프론트엔드
    ├─ AnnotationViewer: Canvas bbox 오버레이 + 오탐지 편집
    ├─ DefectTimelineChart: Recharts 시계열 트렌드
    └─ 알림 페이지 + PDF 리포트 다운로드
```

## 핵심 기능

### 원클릭 분석 UX
1. 드래그앤드롭 업로드 (이미지/영상)
2. "분석 시작" 버튼
3. 실시간 진행률 바 (3초 폴링)
4. 완료 → 결과 페이지 자동 이동

### AI 오탐지 수정 UI (핵심 차별점)
- Canvas API로 bbox 직접 편집/삭제/추가 (드래그)
- 수정된 결과가 최종 보고서에 반영
- 수정 데이터는 모델 재학습에 활용 (1단계 데이터 축적 목적)

### 시계열 균열 추적
- `defect_tracks`: 건물별 균열 생애 기록 (status: monitoring/worsening/stable/repaired/needs_review)
- `defect_track_entries`: 점검마다 폭(mm)/길이(mm)/면적(cm²)/점수 스냅샷
- `change_vs_prev`: 이전 점검 대비 변화량 자동 계산
- GPS/IoU 기반 자동 매칭, 신뢰도 < 0.7 → needs_review

### SegFormer 정밀 면적 측정
- crack 결함에만 선택 적용 (bbox 근사 → 픽셀 마스크로 교체)
- 마스크 PNG → S3 저장 (`segmentation_mask_key`)
- 모델 없으면 pretrained 폴백 (개발 환경)

### 악화 알림
- score_delta > 15 → track.status='worsening' + 이메일 발송 + 앱 내 알림
- 이메일: SMTP (EMAIL_ENABLED=true 시 활성화)
- 앱 내: `defect_alerts` 테이블, GET /api/v1/alerts

### 정량화 공식
```
GSD(cm/px) = 고도(m) × 센서폭(mm) / (초점거리(mm) × 이미지폭(px)) × 100
균열 폭(mm) = bbox 단축(px) × GSD × 10
심각도 점수(0-100) = confidence×40 + 균열폭 비율×30 + 면적 비율×30
```
임계값: 0-29 관찰 | 30-59 주의 | 60-79 경보 | 80-100 긴급

## DB 핵심 테이블
- `tenants`, `users` — 멀티테넌트
- `projects`, `inspections`, `inspection_files` — 점검 관리
- `analysis_jobs`, `analysis_results` — AI 분석 결과 (수치 + 마스크 키 포함)
- `defect_tracks`, `defect_track_entries` — 시계열 추적
- `defect_alerts` — 악화 알림
- `reports`, `subscriptions` — 리포트/결제

## 프로덕션 강화 (Phase 3 완료)

### Celery DLQ
- 최종 실패 태스크 → Redis list `facade.dlq` 자동 보관 (최대 1000건)
- GET /admin/dlq 로 내용 조회
- 큐 분리: analysis / reports / tracking

### PostgreSQL RLS (Row Level Security)
- Alembic 002 마이그레이션으로 10개 테이블에 적용
- `SET app.tenant_id` 커넥션마다 자동 실행 (database.py)
- app_user 롤에만 RLS 정책 적용, migration_user는 BYPASSRLS

### 구조화 로깅
- structlog: 개발=컬러 콘솔, 프로덕션=JSON
- 모든 로그에 `request_id` + `tenant_id` 자동 포함
- RequestLoggingMiddleware: elapsed_ms 포함 HTTP 로그

### Prometheus 메트릭
- GET /metrics — http_requests_total, http_request_duration_seconds
- active_analysis_jobs, dlq_size, crack_detections_total

## API 엔드포인트 요약

```
# 인증
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
GET  /api/v1/auth/me

# 프로젝트 / 점검
GET/POST /api/v1/projects
GET/PUT/DELETE /api/v1/projects/{id}
GET/POST /api/v1/projects/{id}/inspections
POST /api/v1/projects/{id}/inspections/{id}/files        # presigned URL
POST /api/v1/projects/{id}/inspections/{id}/files/confirm # 분석 시작

# 분석
GET /api/v1/analysis/jobs/{id}              # 진행률 폴링
GET /api/v1/analysis/jobs/{id}/results      # 결과 목록

# 균열 추적
GET /api/v1/projects/{id}/defect-tracks
GET /api/v1/defect-tracks/{id}              # 시계열 전체 (차트용)
GET /api/v1/defect-tracks/{id}/compare      # 두 점검 비교
PATCH /api/v1/defect-tracks/{id}            # status 수동 변경

# 알림
GET  /api/v1/alerts
POST /api/v1/alerts/{id}/read
POST /api/v1/alerts/read-all

# 리포트 / 결제
POST /api/v1/inspections/{id}/reports
GET  /api/v1/reports/{id}/download
POST /api/v1/billing/checkout
POST /api/v1/webhooks/stripe

# 운영
GET /health
GET /metrics
GET /admin/dlq
```

## 프론트엔드 페이지 구조

```
/login                    — 로그인 / 회원가입
/projects                 — 프로젝트 목록 (카드 그리드)
/projects/[id]            — 점검 이력 탭 + 균열 추적 탭 (트렌드 차트)
/inspections/[id]         — 파일 업로드 + 분석 뷰어 + 결함 목록
/alerts                   — 악화 알림 목록
```

## 구현 단계 (전체 완료)

| 단계 | 목표 | 상태 |
|------|------|------|
| Phase 0 | docker-compose 환경, DB 스키마, 뼈대 코드 | ✅ |
| Phase 1 | Auth + 업로드 + YOLOv8 추론 + PDF 리포트 + Stripe | ✅ |
| Phase 2 | SegFormer + 시계열 추적 + 악화 알림 | ✅ |
| Phase 3 | DLQ + RLS + 구조화 로깅 + Prometheus | ✅ |
| Frontend | 대시보드 + AnnotationViewer + DefectTimelineChart | ✅ |

## 자동 배포 트리거 (Claude Code Stop 훅)

코드 변경 후 Claude가 응답을 마치면 자동으로 테스트 → 커밋 → 푸시를 실행.

**설정 파일:**
- `.claude/settings.json` — Stop 훅 등록
- `.claude/hooks/test-and-push.sh` — 실행 스크립트

**동작 순서:**
1. 변경된 파일이 없으면 스킵
2. `test_*.py` 파일이 있으면 `pytest -x` 실행 → 실패 시 커밋 중단
3. `frontend/` 변경이 있으면 `tsc --noEmit` 타입체크 → 실패 시 커밋 중단
4. 전체 통과 → `git add -A && git commit && git push origin main`

**비활성화 방법:**
`.claude/settings.json`에서 해당 훅 항목을 삭제하거나 `"disableAllHooks": true` 추가.

**테스트 추가 시 자동 적용:**
`test_*.py` 파일을 생성하면 다음 Stop 시점부터 pytest가 자동 실행됨.

## 보안
- JWT: 15분 access token + 30일 refresh token (localStorage)
- 모든 DB 쿼리: `tenant_id` 필터 강제 (ContextVar 미들웨어) + PostgreSQL RLS 이중 차단
- presigned URL: 유효기간 1시간
- Stripe 웹훅: HMAC 서명 검증
