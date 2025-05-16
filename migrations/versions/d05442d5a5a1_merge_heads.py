"""Merge heads

Revision ID: d05442d5a5a1
Revises: add_configurable_weekend_system, add_user_roles
Create Date: 2025-05-08 14:48:51.000059

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd05442d5a5a1'
down_revision = ('add_configurable_weekend_system', 'add_user_roles')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
