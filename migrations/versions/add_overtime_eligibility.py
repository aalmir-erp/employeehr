"""Add employee overtime eligibility columns

Revision ID: add_overtime_eligibility
Create Date: 2025-05-09 14:16:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_overtime_eligibility'
down_revision = None  # will be populated automatically
branch_labels = None
depends_on = None


def upgrade():
    # Add overtime eligibility columns to employee table
    op.add_column('employee', sa.Column('eligible_for_weekday_overtime', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('employee', sa.Column('eligible_for_weekend_overtime', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('employee', sa.Column('eligible_for_holiday_overtime', sa.Boolean(), nullable=True, server_default='true'))


def downgrade():
    # Remove overtime eligibility columns from employee table
    op.drop_column('employee', 'eligible_for_weekday_overtime')
    op.drop_column('employee', 'eligible_for_weekend_overtime')
    op.drop_column('employee', 'eligible_for_holiday_overtime')