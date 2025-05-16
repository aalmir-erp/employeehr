"""Merge late_minutes and overtime_eligibility branches

Revision ID: 9a518b5ec483
Revises: add_late_minutes_field, add_overtime_eligibility
Create Date: 2025-05-15 16:13:26.165504

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a518b5ec483'
down_revision = ('add_late_minutes_field', 'add_overtime_eligibility')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
