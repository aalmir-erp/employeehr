"""Restore missing production revision marker

Revision ID: 035c401d7d70
Revises: 20260511_status_history
Create Date: 2026-05-12 00:00:00.000000

This repository previously lost the migration file for revision
035c401d7d70, while some deployed databases were already stamped at
that revision. Keep this marker as a no-op bridge so Alembic can resolve
those databases and continue to later migrations.
"""


# revision identifiers, used by Alembic.
revision = '035c401d7d70'
down_revision = '20260511_status_history'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
