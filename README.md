# Facade Inspect

드론 외벽 균열 탐지 B2B SaaS 플랫폼

## 빠른 시작

```bash
cp .env.example .env
docker-compose up
```

- 프론트엔드: http://localhost:3000
- 백엔드 API: http://localhost:8000
- API 문서: http://localhost:8000/docs
- MinIO 콘솔: http://localhost:9001 (minioadmin / minioadmin)

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| AI 추론 | Python + PyTorch + YOLOv8 |
| 백엔드 | FastAPI + SQLAlchemy + Alembic |
| 비동기 | Celery + Redis |
| 스토리지 | MinIO (S3 호환) |
| 프론트엔드 | Next.js 14 + Tailwind CSS |
| DB | PostgreSQL 16 |
| 결제 | Stripe |

## 구현 단계

- **Phase 0** (현재): docker-compose 개발 환경, DB 스키마, 뼈대 코드
- **Phase 1**: MVP — 업로드 → YOLOv8 분석 → 수치(mm) → PDF 리포트 → Stripe
- **Phase 2**: SegFormer + 시계열 균열 추적 + 트렌드 차트
- **Phase 3**: 프로덕션 강화, 비교 뷰어, Enterprise
