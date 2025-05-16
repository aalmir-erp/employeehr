"""Added user roles

Revision ID: add_user_roles
Revises: add_configurable_weekend_system
Create Date: 2025-05-08 14:48:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_user_roles'
down_revision = '08cbacbbc9bf'  # Reference previous migration
branch_labels = None
depends_on = None


def upgrade():
    # Add role column to user table
    op.add_column('user', sa.Column('role', sa.String(20), server_default='employee'))
    op.add_column('user', sa.Column('department', sa.String(64), nullable=True))
    
    # Set admin users to have 'admin' role
    op.execute("""
    UPDATE "user" 
    SET role = 'admin' 
    WHERE is_admin = TRUE
    """)
    
    # Create index on role for faster querying
    op.create_index(op.f('ix_user_role'), 'user', ['role'], unique=False)


def downgrade():
    # Drop the role column and index
    op.drop_index(op.f('ix_user_role'), table_name='user')
    op.drop_column('user', 'department')
    op.drop_column('user', 'role')