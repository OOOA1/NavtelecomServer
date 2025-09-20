"""Create idempotency cache table

Revision ID: 20250101_000004
Revises: 20250101_000003
Create Date: 2025-01-01 00:00:04.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250101_000004'
down_revision = '20250101_000003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create idempotency cache table."""
    op.create_table('idempotency_cache',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('cache_key', sa.String(255), nullable=False),
        sa.Column('response_data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cache_key')
    )
    
    # Create index for fast lookups
    op.create_index('idx_idempotency_cache_key', 'idempotency_cache', ['cache_key'])
    op.create_index('idx_idempotency_cache_created_at', 'idempotency_cache', ['created_at'])


def downgrade() -> None:
    """Drop idempotency cache table."""
    op.drop_index('idx_idempotency_cache_created_at', table_name='idempotency_cache')
    op.drop_index('idx_idempotency_cache_key', table_name='idempotency_cache')
    op.drop_table('idempotency_cache')

