"""Add late_minutes field to AttendanceRecord

Revision ID: add_late_minutes_field
Revises: add_ai_assistant_config
Create Date: 2025-05-09 07:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_late_minutes_field'
down_revision = 'add_ai_assistant_config'
branch_labels = None
depends_on = None


def upgrade():
    # Add late_minutes column to attendance_record table with default value of 0
    op.add_column('attendance_record', sa.Column('late_minutes', sa.Integer(), nullable=True, server_default='0'))
    
    # Update existing records to set late_minutes to 0
    op.execute("UPDATE attendance_record SET late_minutes = 0 WHERE late_minutes IS NULL")
    
    # Then make it not nullable
    op.alter_column('attendance_record', 'late_minutes', nullable=False, existing_type=sa.Integer(), server_default='0')


def downgrade():
    # Remove late_minutes column
    op.drop_column('attendance_record', 'late_minutes')