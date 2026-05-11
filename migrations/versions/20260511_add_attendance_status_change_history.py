"""Add attendance status change history

Revision ID: 20260511_status_history
Revises: add_attendance_notifications
Create Date: 2026-05-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260511_status_history'
down_revision = 'add_attendance_notifications'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'attendance_status_change_history',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('attendance_record_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('check_in', sa.DateTime(), nullable=True),
        sa.Column('check_out', sa.DateTime(), nullable=True),
        sa.Column('previous_status', sa.String(length=20), nullable=False),
        sa.Column('new_status', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=False),
        sa.Column('hours_old_threshold', sa.Integer(), nullable=True),
        sa.Column('checkout_window_hours', sa.Integer(), nullable=True),
        sa.Column('converted_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['attendance_record_id'], ['attendance_record.id'], name='fk_attendance_status_history_record'),
        sa.ForeignKeyConstraint(['employee_id'], ['employee.id'], name='fk_attendance_status_history_employee'),
    )
    op.create_index(
        'ix_attendance_status_history_record_id',
        'attendance_status_change_history',
        ['attendance_record_id']
    )
    op.create_index(
        'ix_attendance_status_history_employee_date',
        'attendance_status_change_history',
        ['employee_id', 'date']
    )
    op.create_index(
        'ix_attendance_status_history_converted_at',
        'attendance_status_change_history',
        ['converted_at']
    )


def downgrade():
    op.drop_index('ix_attendance_status_history_converted_at', table_name='attendance_status_change_history')
    op.drop_index('ix_attendance_status_history_employee_date', table_name='attendance_status_change_history')
    op.drop_index('ix_attendance_status_history_record_id', table_name='attendance_status_change_history')
    op.drop_table('attendance_status_change_history')
