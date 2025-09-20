"""Expand raw_frames table with new fields

Revision ID: 20250101_000002
Revises: 20250101_000001
Create Date: 2025-01-01 00:00:02.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250101_000002'
down_revision = '20250101_000001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Expand: Add new fields to raw_frames table."""
    
    # 1. Add new columns with default values (safe)
    op.add_column('raw_frames', sa.Column('new_field', sa.String(255), nullable=True))
    op.add_column('raw_frames', sa.Column('new_timestamp', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('raw_frames', sa.Column('processing_version', sa.String(50), nullable=True, default='v1'))
    
    # 2. Create new indexes CONCURRENTLY (safe, non-blocking)
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_frames_new_field ON raw_frames(new_field)')
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_frames_new_timestamp ON raw_frames(new_timestamp)')
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_raw_frames_processing_version ON raw_frames(processing_version)')
    
    # 3. Create new table for enhanced processing
    op.create_table('raw_frames_enhanced',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('raw_frame_id', sa.UUID(), nullable=False),
        sa.Column('device_hint', sa.String(255), nullable=False),
        sa.Column('enhanced_data', sa.JSON(), nullable=True),
        sa.Column('processing_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['raw_frame_id'], ['raw_frames.id'], ondelete='CASCADE')
    )
    
    # 4. Create indexes for new table
    op.create_index('idx_raw_frames_enhanced_raw_frame_id', 'raw_frames_enhanced', ['raw_frame_id'])
    op.create_index('idx_raw_frames_enhanced_device_hint', 'raw_frames_enhanced', ['device_hint'])
    op.create_index('idx_raw_frames_enhanced_created_at', 'raw_frames_enhanced', ['created_at'])
    
    # 5. Create new partition for raw_frames (if using partitioning)
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw_frames_2025_01 PARTITION OF raw_frames
        FOR VALUES FROM ('2025-01-01') TO ('2025-02-01')
    """)


def downgrade() -> None:
    """Contract: Remove new fields (this will be a separate migration)."""
    
    # Note: In expand migrations, we typically don't implement downgrade
    # The downgrade will be handled by the corresponding contract migration
    
    # 1. Drop indexes
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_raw_frames_processing_version')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_raw_frames_new_timestamp')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS idx_raw_frames_new_field')
    
    # 2. Drop new table
    op.drop_table('raw_frames_enhanced')
    
    # 3. Drop new columns
    op.drop_column('raw_frames', 'processing_version')
    op.drop_column('raw_frames', 'new_timestamp')
    op.drop_column('raw_frames', 'new_field')
    
    # 4. Drop new partition
    op.execute('DROP TABLE IF EXISTS raw_frames_2025_01')

