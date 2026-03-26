"""002: PostgreSQL RLS + 성능 인덱스

Row Level Security(RLS)를 활성화해 DB 레이어에서 테넌트 격리를 강제한다.
앱 레이어의 tenant_id 필터가 누락되더라도 다른 테넌트 데이터에 접근 불가.

설계:
  - app_user (애플리케이션 롤): SELECT/INSERT/UPDATE/DELETE 허용 + RLS 적용
  - migration_user (마이그레이션 롤): BYPASSRLS 권한 (Alembic 실행용)
  - 각 테이블에 ENABLE ROW LEVEL SECURITY + FORCE ROW LEVEL SECURITY
  - 정책: current_setting('app.tenant_id')::uuid = tenant_id
  - 앱에서 각 DB 커넥션 시작 시 SET app.tenant_id = '<uuid>' 실행

Revision ID: 002
Revises: 001
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

# RLS를 적용할 테이블 목록 (tenant_id 컬럼 있는 테이블)
_TENANT_TABLES = [
    "projects",
    "inspections",
    "inspection_files",
    "analysis_jobs",
    "analysis_results",
    "defect_tracks",
    "defect_track_entries",
    "reports",
    "subscriptions",
    "defect_alerts",
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. 애플리케이션 전용 롤 생성 (없으면)
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
                CREATE ROLE app_user LOGIN PASSWORD 'change_in_production';
            END IF;
        END
        $$;
    """))

    # 2. 테이블별 RLS 활성화 + 정책 생성
    for table in _TENANT_TABLES:
        # 테넌트 격리 정책 (app_user에만 적용)
        conn.execute(sa.text(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        """))

        conn.execute(sa.text(f"""
            DROP POLICY IF EXISTS tenant_isolation ON {table};
            CREATE POLICY tenant_isolation ON {table}
                AS PERMISSIVE
                FOR ALL
                TO app_user
                USING (
                    tenant_id = current_setting('app.tenant_id', true)::uuid
                )
                WITH CHECK (
                    tenant_id = current_setting('app.tenant_id', true)::uuid
                );
        """))

    # 3. 성능 인덱스 (조회 최적화)
    op.create_index("ix_analysis_results_severity_score",
                    "analysis_results", ["severity_score"])
    op.create_index("ix_defect_track_entries_inspection_date",
                    "defect_track_entries", ["track_id", "inspection_date"])
    op.create_index("ix_defect_alerts_tenant_unread",
                    "defect_alerts", ["tenant_id", "is_read"])
    op.create_index("ix_inspections_project_date",
                    "inspections", ["project_id", "inspection_date"])


def downgrade() -> None:
    conn = op.get_bind()

    # 인덱스 제거
    op.drop_index("ix_analysis_results_severity_score", "analysis_results")
    op.drop_index("ix_defect_track_entries_inspection_date", "defect_track_entries")
    op.drop_index("ix_defect_alerts_tenant_unread", "defect_alerts")
    op.drop_index("ix_inspections_project_date", "inspections")

    # RLS 비활성화
    for table in _TENANT_TABLES:
        conn.execute(sa.text(f"""
            DROP POLICY IF EXISTS tenant_isolation ON {table};
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """))
