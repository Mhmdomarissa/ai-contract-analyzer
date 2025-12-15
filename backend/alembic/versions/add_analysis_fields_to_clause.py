"""add_analysis_fields_to_clause

Revision ID: add_analysis_fields
Revises: 0e180067cb32
Create Date: 2025-01-20 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'add_analysis_fields'
down_revision = '2ca11903efb8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add analysis_results JSONB column
    op.add_column('clauses', sa.Column('analysis_results', JSONB(), nullable=True))
    # Add analysis_status string column
    op.add_column('clauses', sa.Column('analysis_status', sa.String(length=32), nullable=True))


def downgrade() -> None:
    # Remove analysis columns
    op.drop_column('clauses', 'analysis_status')
    op.drop_column('clauses', 'analysis_results')

