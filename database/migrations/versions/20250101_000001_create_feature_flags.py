"""Create feature flags table

Revision ID: 20250101_000001
Revises: 
Create Date: 2025-01-01 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250101_000001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create feature flags table."""
    op.create_table('feature_flags',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('flag_name', sa.String(255), nullable=False),
        sa.Column('flag_value', sa.Boolean(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, default='active'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('flag_name')
    )
    
    # Create index for fast lookups
    op.create_index('idx_feature_flags_name', 'feature_flags', ['flag_name'])
    op.create_index('idx_feature_flags_status', 'feature_flags', ['status'])


def downgrade() -> None:
    """Drop feature flags table."""
    op.drop_index('idx_feature_flags_status', table_name='feature_flags')
    op.drop_index('idx_feature_flags_name', table_name='feature_flags')
    op.drop_table('feature_flags')

