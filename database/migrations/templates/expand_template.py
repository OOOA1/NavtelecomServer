"""
Template for expand migrations (zero-downtime additions).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Example expand migration template
# This template shows how to safely add new columns, tables, and indexes

def upgrade() -> None:
    """Expand: Add new columns, tables, indexes without breaking existing functionality."""
    
    # 1. Add new columns with default values (safe)
    op.add_column('raw_frames', sa.Column('new_field', sa.String(255), nullable=True))
    op.add_column('raw_frames', sa.Column('new_timestamp', sa.TIMESTAMP(timezone=True), nullable=True))
    
    # 2. Create new tables (safe)
    op.create_table('new_feature_table',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('device_id', sa.String(255), nullable=False),
        sa.Column('feature_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 3. Create indexes CONCURRENTLY (safe, non-blocking)
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_frames_new_field ON raw_frames(new_field)')
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_frames_new_timestamp ON raw_frames(new_timestamp)')
    
    # 4. Create new partitions (if using partitioning)
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw_frames_2025_01 PARTITION OF raw_frames
        FOR VALUES FROM ('2025-01-01') TO ('2025-02-01')
    """)
    
    # 5. Add new constraints (if needed, but be careful)
    # op.create_check_constraint('ck_new_field_format', 'raw_frames', 'new_field ~ \'^[A-Z0-9]+$\'')


def downgrade() -> None:
    """Contract: Remove new additions (this will be a separate migration)."""
    
    # Note: In expand migrations, we typically don't implement downgrade
    # The downgrade will be handled by the corresponding contract migration
    
    # 1. Drop indexes
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_raw_frames_new_field')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_raw_frames_new_timestamp')
    
    # 2. Drop new columns
    op.drop_column('raw_frames', 'new_timestamp')
    op.drop_column('raw_frames', 'new_field')
    
    # 3. Drop new tables
    op.drop_table('new_feature_table')
    
    # 4. Drop partitions
    op.execute('DROP TABLE IF EXISTS raw_frames_2025_01')

