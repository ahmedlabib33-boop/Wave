"""PostGIS generated geography and spatial index for PostgreSQL deployments."""

from alembic import op

revision = "2_postgis"
down_revision = "26eefa3e5657"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        op.execute("""ALTER TABLE observations ADD COLUMN geom geography(Point,4326)
          GENERATED ALWAYS AS (CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL
          THEN ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography ELSE NULL END) STORED""")
        op.execute("CREATE INDEX ix_observations_geography ON observations USING gist(geom)")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX ix_observations_geography")
        op.execute("ALTER TABLE observations DROP COLUMN geom")
