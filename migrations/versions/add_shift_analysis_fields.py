"""Add shift analysis fields to attendance record

Revision ID: add_shift_analysis_fields
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_shift_analysis_fields'
down_revision = 'a50784d34b84'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns
    op.add_column('attendance_record', sa.Column('shift_type', sa.String(20), nullable=True))
    op.add_column('attendance_record', sa.Column('total_duration', sa.Float(), nullable=True))
    
    # Update existing records with default values
    op.execute("UPDATE attendance_record SET shift_type = 'day' WHERE shift_type IS NULL")
    op.execute("UPDATE attendance_record SET total_duration = 0.0 WHERE total_duration IS NULL")


def downgrade():
    # Drop the added columns
    op.drop_column('attendance_record', 'shift_type')
    op.drop_column('attendance_record', 'total_duration')