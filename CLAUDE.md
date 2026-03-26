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

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| AI 추론 | Python + PyTorch + YOLOv8 (→ Phase 2: SegFormer) |
| 백엔드 | FastAPI + SQLAlchemy(async) + Alembic |
| 비동기 | Celery + Redis |
| 스토리지 | MinIO (로컬) / AWS S3 (프로덕션) |
| 프론트엔드 | Next.js 14 + Tailwind CSS |
| DB | PostgreSQL 16 |
| 결제 | Stripe |

## 아키텍처 요약

```
드론 이미지/영상
    │ 업로드 (presigned S3 URL)
    ▼
FastAPI 백엔드 → Celery 태스크 enqueue
    │
    ▼
Celery 워커 (AI 추론)
    ├─ YOLOv8 배치 추론 → bbox + confidence
    ├─ GSD 계산 → 균열 폭/길이/면적(mm/cm²) 환산
    ├─ severity_score 0-100 계산
    └─ 어노테이션 이미지 → S3 저장
    │
    ▼
결과 뷰어 (Next.js)
    ├─ 어노테이션 이미지 + bbox 오버레이
    ├─ 오탐지 수동 수정 (마우스 드래그로 bbox 편집/삭제)
    └─ 보고서/도면 다운로드 (PDF)
```

## 핵심 기능

### 원클릭 분석 UX
1. 드래그앤드롭 업로드
2. "분석 시작" 버튼
3. 실시간 진행률 바 (3초 폴링)
4. 완료 → 결과 페이지 자동 이동

### AI 오탐지 수정 UI (핵심 차별점)
- 결과 이미지 위에서 bbox 직접 편집/삭제/추가
- 수정된 결과가 최종 보고서에 반영
- 수정 데이터는 모델 재학습에 활용 (1단계 데이터 축적 목적)

### 시계열 균열 추적
- `defect_tracks`: 건물별 균열 생애 기록
- `defect_track_entries`: 점검마다 폭(mm)/길이(mm)/면적(cm²)/점수 스냅샷
- `change_vs_prev`: 이전 점검 대비 변화량 자동 계산

### 정량화 공식
```
GSD(cm/px) = 고도(m) × 센서폭(mm) / (초점거리(mm) × 이미지폭(px)) × 100
균열 폭(mm) = bbox 단축(px) × GSD × 10
심각도 점수(0-100) = confidence×40 + 균열폭비율×30 + 면적비율×30
```
임계값: 0-29 관찰 | 30-59 주의 | 60-79 경보 | 80-100 긴급

## DB 핵심 테이블
- `tenants`, `users` — 멀티테넌트
- `projects`, `inspections`, `inspection_files` — 점검 관리
- `analysis_jobs`, `analysis_results` — AI 분석 결과 (수치 포함)
- `defect_tracks`, `defect_track_entries` — 시계열 추적
- `reports`, `subscriptions` — 리포트/결제

## 구현 단계

| 단계 | 목표 |
|------|------|
| Phase 0 ✅ | docker-compose 환경, DB 스키마, 뼈대 코드 |
| Phase 1 | Auth + 업로드 + YOLOv8 추론 + **오탐지 수정 UI** + PDF 리포트 + Stripe |
| Phase 2 | SegFormer + 시계열 추적 + 트렌드 차트 |
| Phase 3 | 프로덕션 강화, 비교 뷰어, Enterprise |

## 보안
- JWT: 15분 access token + 30일 refresh token (HttpOnly 쿠키)
- 모든 DB 쿼리: `tenant_id` 필터 강제 (ContextVar 미들웨어)
- presigned URL: 유효기간 1시간
