"""Contract raw_frames table - remove old fields

Revision ID: 20250101_000003
Revises: 20250101_000002
Create Date: 2025-01-01 00:00:03.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250101_000003'
down_revision = '20250101_000002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Contract: Remove old fields after new fields are stable."""
    
    # 1. Drop old indexes (safe)
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_raw_frames_old_field')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_raw_frames_old_timestamp')
    
    # 2. Drop old columns (safe after new columns are in use)
    op.drop_column('raw_frames', 'old_timestamp')
    op.drop_column('raw_frames', 'old_field')
    
    # 3. Drop old tables (safe after data migration)
    op.drop_table('raw_frames_legacy')
    
    # 4. Drop old partitions (safe after data migration)
    op.execute('DROP TABLE IF EXISTS raw_frames_2024_12')
    
    # 5. Remove old constraints
    op.drop_constraint('ck_old_field_format', 'raw_frames', type_='check')


def downgrade() -> None:
    """Expand: Re-add old features (for rollback)."""
    
    # 1. Re-add old columns
    op.add_column('raw_frames', sa.Column('old_field', sa.String(255), nullable=True))
    op.add_column('raw_frames', sa.Column('old_timestamp', sa.TIMESTAMP(timezone=True), nullable=True))
    
    # 2. Re-create old tables
    op.create_table('raw_frames_legacy',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('device_hint', sa.String(255), nullable=False),
        sa.Column('legacy_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 3. Re-create old indexes
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_frames_old_field ON raw_frames(old_field)')
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_frames_old_timestamp ON raw_frames(old_timestamp)')
    
    # 4. Re-create old partitions
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw_frames_2024_12 PARTITION OF raw_frames
        FOR VALUES FROM ('2024-12-01') TO ('2025-01-01')
    """)
    
    # 5. Re-add old constraints
    op.create_check_constraint('ck_old_field_format', 'raw_frames', 'old_field ~ \'^[A-Z0-9]+$\'')

