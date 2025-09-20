"""
Template for contract migrations (safe removal of old features).
"""
from alembic import op
import sqlalchemy as sa

# Example contract migration template
# This template shows how to safely remove old columns, tables, and indexes

def upgrade() -> None:
    """Contract: Remove old columns, tables, indexes after new features are stable."""
    
    # 1. Drop old indexes (safe)
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_raw_frames_old_field')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_raw_frames_old_timestamp')
    
    # 2. Drop old columns (safe after new columns are in use)
    op.drop_column('raw_frames', 'old_timestamp')
    op.drop_column('raw_frames', 'old_field')
    
    # 3. Drop old tables (safe after data migration)
    op.drop_table('old_feature_table')
    
    # 4. Drop old partitions (safe after data migration)
    op.execute('DROP TABLE IF EXISTS raw_frames_2024_12')
    
    # 5. Remove old constraints
    # op.drop_constraint('ck_old_field_format', 'raw_frames', type_='check')


def downgrade() -> None:
    """Expand: Re-add old features (for rollback)."""
    
    # 1. Re-add old columns
    op.add_column('raw_frames', sa.Column('old_field', sa.String(255), nullable=True))
    op.add_column('raw_frames', sa.Column('old_timestamp', sa.TIMESTAMP(timezone=True), nullable=True))
    
    # 2. Re-create old tables
    op.create_table('old_feature_table',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('device_id', sa.String(255), nullable=False),
        sa.Column('old_data', sa.JSON(), nullable=True),
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

