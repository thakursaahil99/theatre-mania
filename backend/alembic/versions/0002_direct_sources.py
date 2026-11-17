"""direct public-domain sources: movies.external_id, video_assets.playback_url

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch mode so the same migration works on SQLite (native dev) and Postgres.
    with op.batch_alter_table("movies") as batch:
        batch.add_column(sa.Column("external_id", sa.String(160)))
        batch.create_index("ix_movies_external_id", ["external_id"], unique=True)
    with op.batch_alter_table("video_assets") as batch:
        batch.add_column(sa.Column("playback_url", sa.String(1024)))


def downgrade() -> None:
    with op.batch_alter_table("video_assets") as batch:
        batch.drop_column("playback_url")
    with op.batch_alter_table("movies") as batch:
        batch.drop_index("ix_movies_external_id")
        batch.drop_column("external_id")
