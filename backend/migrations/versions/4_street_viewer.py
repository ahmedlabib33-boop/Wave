"""Add street metadata and playback evidence; preserve every existing table and record."""

from alembic import op
import sqlalchemy as sa

revision = "4_street_viewer"
down_revision = "3_discovery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "street_segments",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_table(
        "street_queries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
    )
    op.create_table(
        "camera_views",
        sa.Column("camera_id", sa.String(100), sa.ForeignKey("cameras.id"), primary_key=True),
        sa.Column("street_ids", sa.JSON(), nullable=False),
        sa.Column("footprint", sa.JSON(), nullable=True),
        sa.Column("coverage_evidence", sa.Text(), nullable=True),
        sa.Column("live_declared", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        *[sa.Column(k, sa.DateTime(timezone=True), nullable=True) for k in (
            "checked_at", "last_frame_at", "playback_confirmed_at", "retry_at"
        )],
        *[sa.Column(k, sa.Integer(), nullable=False) for k in (
            "decoded_frames", "rendered_frames", "failures"
        )],
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("configuration_hash", sa.String(64), nullable=True),
    )
