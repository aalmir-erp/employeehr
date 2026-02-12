"""Create attendance_notification table

Revision ID: add_attendance_notifications
Revises: 76958586561d
Create Date: 2025-05-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_attendance_notifications'
down_revision = '76958586561d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'attendance_notification',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('attendance_log_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='hr'),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['attendance_log_id'], ['attendance_log.id'], name='fk_attendance_notification_log'),
    )

    op.create_index(
        'ix_attendance_notification_role_is_read',
        'attendance_notification',
        ['role', 'is_read']
    )
    op.create_index(
        'ix_attendance_notification_created_at',
        'attendance_notification',
        ['created_at']
    )


def downgrade():
    op.drop_index('ix_attendance_notification_created_at', table_name='attendance_notification')
    op.drop_index('ix_attendance_notification_role_is_read', table_name='attendance_notification')
    op.drop_table('attendance_notification')
