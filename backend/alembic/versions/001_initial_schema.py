"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
import uuid

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ENUM types
    op.execute("CREATE TYPE plantype AS ENUM ('trial','starter','pro','enterprise')")
    op.execute("CREATE TYPE userrole AS ENUM ('admin','manager','viewer')")
    op.execute("CREATE TYPE projectstatus AS ENUM ('active','archived')")
    op.execute("CREATE TYPE inspectionstatus AS ENUM ('pending','uploading','queued','processing','completed','failed')")
    op.execute("CREATE TYPE filetype AS ENUM ('image','video')")
    op.execute("CREATE TYPE jobstatus AS ENUM ('queued','running','completed','failed')")
    op.execute("CREATE TYPE defecttype AS ENUM ('crack','spalling','efflorescence','stain','delamination','other')")
    op.execute("CREATE TYPE severitylevel AS ENUM ('low','medium','high','critical')")
    op.execute("CREATE TYPE trackstatus AS ENUM ('monitoring','worsening','stable','repaired')")
    op.execute("CREATE TYPE reportstatus AS ENUM ('pending','generating','completed','failed')")
    op.execute("CREATE TYPE subscriptionplan AS ENUM ('starter','pro','enterprise')")
    op.execute("CREATE TYPE subscriptionstatus AS ENUM ('trialing','active','past_due','canceled','unpaid')")

    op.create_table("tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("plan", sa.Enum("trial","starter","pro","enterprise", name="plantype"), default="trial"),
        sa.Column("stripe_customer_id", sa.String(100), unique=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("max_projects", sa.Integer, default=5),
        sa.Column("max_storage_gb", sa.Numeric(10, 2), default=5.0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("admin","manager","viewer", name="userrole"), default="viewer"),
        sa.Column("full_name", sa.String(255)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email"),
    )

    op.create_table("projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text),
        sa.Column("building_type", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.Enum("active","archived", name="projectstatus"), default="active"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("inspections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("label", sa.String(255)),
        sa.Column("drone_model", sa.String(100)),
        sa.Column("flight_altitude_m", sa.Numeric(6, 2)),
        sa.Column("inspection_date", sa.Date),
        sa.Column("status", sa.Enum("pending","uploading","queued","processing","completed","failed", name="inspectionstatus"), default="pending"),
        sa.Column("file_count", sa.Integer, default=0),
        sa.Column("total_size_bytes", sa.BigInteger, default=0),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("inspection_files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("inspection_id", UUID(as_uuid=True), sa.ForeignKey("inspections.id"), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("original_filename", sa.String(500)),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("file_type", sa.Enum("image","video", name="filetype")),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("gps_lat", sa.Numeric(10, 7)),
        sa.Column("gps_lon", sa.Numeric(10, 7)),
        sa.Column("altitude_m", sa.Numeric(8, 2)),
        sa.Column("focal_length_mm", sa.Numeric(8, 3)),
        sa.Column("sensor_width_mm", sa.Numeric(8, 3)),
        sa.Column("image_width_px", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("analysis_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("inspection_id", UUID(as_uuid=True), sa.ForeignKey("inspections.id"), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("celery_task_id", sa.String(255), unique=True),
        sa.Column("model_version", sa.String(50)),
        sa.Column("status", sa.Enum("queued","running","completed","failed", name="jobstatus"), default="queued"),
        sa.Column("progress_pct", sa.SmallInteger, default=0),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("analysis_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("analysis_jobs.id"), nullable=False, index=True),
        sa.Column("inspection_file_id", UUID(as_uuid=True), sa.ForeignKey("inspection_files.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("defect_type", sa.Enum("crack","spalling","efflorescence","stain","delamination","other", name="defecttype")),
        sa.Column("severity_score", sa.SmallInteger, default=0),
        sa.Column("severity", sa.Enum("low","medium","high","critical", name="severitylevel")),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("bounding_box", JSONB),
        sa.Column("crack_width_mm", sa.Numeric(8, 3)),
        sa.Column("crack_length_mm", sa.Numeric(10, 3)),
        sa.Column("crack_area_cm2", sa.Numeric(12, 4)),
        sa.Column("affected_area_pct", sa.Numeric(6, 4)),
        sa.Column("annotated_image_key", sa.String(1000)),
        sa.Column("segmentation_mask_key", sa.String(1000)),
        sa.Column("metadata", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analysis_results_tenant_severity", "analysis_results", ["tenant_id", "severity"])

    op.create_table("defect_tracks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("first_seen_at", sa.Date),
        sa.Column("location_zone", sa.String(100)),
        sa.Column("representative_image_key", sa.String(1000)),
        sa.Column("status", sa.Enum("monitoring","worsening","stable","repaired", name="trackstatus"), default="monitoring"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("defect_track_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("track_id", UUID(as_uuid=True), sa.ForeignKey("defect_tracks.id"), nullable=False, index=True),
        sa.Column("analysis_result_id", UUID(as_uuid=True), sa.ForeignKey("analysis_results.id"), unique=True),
        sa.Column("inspection_id", UUID(as_uuid=True), sa.ForeignKey("inspections.id"), nullable=False),
        sa.Column("inspection_date", sa.Date, index=True),
        sa.Column("severity_score", sa.SmallInteger, default=0),
        sa.Column("crack_width_mm", sa.Numeric(8, 3)),
        sa.Column("crack_length_mm", sa.Numeric(10, 3)),
        sa.Column("crack_area_cm2", sa.Numeric(12, 4)),
        sa.Column("change_vs_prev", JSONB),
        sa.Column("annotated_image_key", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("inspection_id", UUID(as_uuid=True), sa.ForeignKey("inspections.id"), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("generated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("storage_key", sa.String(1000)),
        sa.Column("version", sa.SmallInteger, default=1),
        sa.Column("status", sa.Enum("pending","generating","completed","failed", name="reportstatus"), default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table("subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), unique=True, nullable=False),
        sa.Column("stripe_subscription_id", sa.String(100), unique=True),
        sa.Column("stripe_price_id", sa.String(100)),
        sa.Column("plan", sa.Enum("starter","pro","enterprise", name="subscriptionplan")),
        sa.Column("status", sa.Enum("trialing","active","past_due","canceled","unpaid", name="subscriptionstatus")),
        sa.Column("current_period_start", sa.DateTime(timezone=True)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("cancel_at_period_end", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("reports")
    op.drop_table("defect_track_entries")
    op.drop_table("defect_tracks")
    op.drop_table("analysis_results")
    op.drop_table("analysis_jobs")
    op.drop_table("inspection_files")
    op.drop_table("inspections")
    op.drop_table("projects")
    op.drop_table("users")
    op.drop_table("tenants")
    for t in ["plantype","userrole","projectstatus","inspectionstatus","filetype",
              "jobstatus","defecttype","severitylevel","trackstatus","reportstatus",
              "subscriptionplan","subscriptionstatus"]:
        op.execute(f"DROP TYPE IF EXISTS {t}")
