"""Add camera investigation records without altering existing data or configuration."""

from alembic import op
import sqlalchemy as sa

revision = "3_discovery"
down_revision = "2_postgis"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "camera_candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("discovery_key", sa.String(160), nullable=False, unique=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("permission_state", sa.String(40), nullable=False),
        sa.Column("permission_evidence", sa.Text(), nullable=True),
        sa.Column("permission_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url_env", sa.String(100), nullable=True),
        sa.Column("protocol", sa.String(20), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_status", sa.String(40), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("frame_width", sa.Integer(), nullable=True),
        sa.Column("frame_height", sa.Integer(), nullable=True),
        sa.Column("stream_fingerprint", sa.String(64), nullable=True),
        sa.Column("camera_id", sa.String(100), sa.ForeignKey("cameras.id"), nullable=True),
    )
    op.create_table(
        "discovery_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("candidate_id", sa.String(64), sa.ForeignKey("camera_candidates.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("returned_count", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("discovery_runs")
    op.drop_table("camera_candidates")
