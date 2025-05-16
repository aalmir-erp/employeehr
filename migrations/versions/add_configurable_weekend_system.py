"""Add configurable weekend system

Revision ID: add_configurable_weekend_system
Revises: 08cbacbbc9bf
Create Date: 2023-05-08 14:36:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_configurable_weekend_system'
down_revision = '08cbacbbc9bf'
branch_labels = None
depends_on = None  # Independent from add_user_roles migration


def upgrade():
    # Skip adding weekend_days columns as they already exist in the database
    # op.add_column('employee', sa.Column('weekend_days', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    # op.add_column('shift', sa.Column('weekend_days', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    
    # Skip creating SystemConfig table as it already exists
    # op.create_table('system_config', ...)
    
    # Check if a system config entry already exists
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT COUNT(*) FROM system_config"))
    count = result.scalar()
    
    if count == 0:
        # Create a default system configuration only if the table is empty
        conn.execute(sa.text("""
        INSERT INTO system_config (system_name, weekend_days, default_work_hours, timezone, date_format, time_format, created_at, updated_at)
        VALUES ('MIR Attendance Management System', '[5, 6]', 8.0, 'Asia/Dubai', 'DD/MM/YYYY', 'HH:mm:ss', now(), now())
        """))


def downgrade():
    # Skip dropping SystemConfig table since it's being managed by other code
    pass
    # The following lines are commented out as we're skipping these operations
    # op.drop_table('system_config')
    # op.drop_column('shift', 'weekend_days')
    # op.drop_column('employee', 'weekend_days')