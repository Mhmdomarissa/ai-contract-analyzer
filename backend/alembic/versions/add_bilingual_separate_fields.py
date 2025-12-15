"""add_bilingual_separate_fields

Revision ID: add_bilingual_separate
Revises: add_analysis_fields
Create Date: 2025-01-20 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_bilingual_separate'
down_revision = 'add_analysis_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Columns may already exist from previous migration
    # Use IF NOT EXISTS equivalent by checking first
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='clauses' AND column_name IN ('arabic_text', 'is_bilingual')
    """))
    existing = [row[0] for row in result]
    
    # Add arabic_text column for storing Arabic version separately (if not exists)
    if 'arabic_text' not in existing:
        op.add_column('clauses', sa.Column('arabic_text', sa.Text(), nullable=True))
    
    # Add is_bilingual flag to indicate if clause has both languages (if not exists)
    if 'is_bilingual' not in existing:
        op.add_column('clauses', sa.Column('is_bilingual', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove bilingual columns
    op.drop_column('clauses', 'is_bilingual')
    op.drop_column('clauses', 'arabic_text')

