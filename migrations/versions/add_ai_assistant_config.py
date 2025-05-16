"""Add AI Assistant configuration columns to SystemConfig

Revision ID: add_ai_assistant_config
Revises: add_configurable_weekend_system
Create Date: 2025-05-08 15:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_ai_assistant_config'
down_revision = 'd05442d5a5a1'  # Use the other head revision
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to system_config table
    op.add_column('system_config', sa.Column('openai_api_key', sa.String(length=256), nullable=True))
    op.add_column('system_config', sa.Column('ai_assistant_enabled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('system_config', sa.Column('ai_model', sa.String(length=64), server_default='gpt-4o', nullable=False))


def downgrade():
    # Remove columns if needed to downgrade
    op.drop_column('system_config', 'ai_model')
    op.drop_column('system_config', 'ai_assistant_enabled')
    op.drop_column('system_config', 'openai_api_key')