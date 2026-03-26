"""add favorites and access log

Revision ID: a1b2c3d4e5f6
Revises: 70a0cd85ce59
Create Date: 2026-03-26 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '70a0cd85ce59'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wb_source_favorites',
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['wb_sources.id']),
        sa.PrimaryKeyConstraint('source_id'),
    )
    op.create_table(
        'wb_source_access_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('accessed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['wb_sources.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_wb_source_access_log_source_id'),
        'wb_source_access_log',
        ['source_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_wb_source_access_log_source_id'), table_name='wb_source_access_log')
    op.drop_table('wb_source_access_log')
    op.drop_table('wb_source_favorites')
