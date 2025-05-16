"""Enhance attendance import and deletion

Revision ID: c45e6bc23f9a
Revises: 9a846ad5a73d
Create Date: 2025-05-07 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c45e6bc23f9a'
down_revision = '9a846ad5a73d'
branch_labels = None
depends_on = None


def upgrade():
    # Add an index to attendance_log to improve duplicate detection
    op.create_index('ix_attendance_log_employee_timestamp_log_type', 'attendance_log', 
                   ['employee_id', 'timestamp', 'log_type'], unique=True)
    
    # Add an index to attendance_record to improve search by date range
    op.create_index('ix_attendance_record_date', 'attendance_record', ['date'], unique=False)
    
    # Add an index to attendance_record for employee_id and date
    op.create_index('ix_attendance_record_employee_id_date', 'attendance_record', 
                   ['employee_id', 'date'], unique=False)


def downgrade():
    # Remove the indexes in reverse order
    op.drop_index('ix_attendance_record_employee_id_date', table_name='attendance_record')
    op.drop_index('ix_attendance_record_date', table_name='attendance_record')
    op.drop_index('ix_attendance_log_employee_timestamp_log_type', table_name='attendance_log')