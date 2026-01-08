"""Create contract processing tables

Revision ID: create_upload_extraction_schema
Revises: 
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'create_upload_extraction_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create contracts table
    op.create_table(
        'contracts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('file_type', sa.String(50), nullable=False),
        sa.Column('file_size', sa.Integer, nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='processing'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_contracts_status', 'contracts', ['status'])
    op.create_index('ix_contracts_created_at', 'contracts', ['created_at'])
    
    # Create contract_versions table
    op.create_table(
        'contract_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('contract_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_number', sa.Integer, nullable=False),
        sa.Column('raw_text', sa.Text, nullable=False),
        sa.Column('parsed_text', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_contract_versions_contract_id', 'contract_versions', ['contract_id'])
    
    # Create parties table
    op.create_table(
        'parties',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('contract_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_parties_contract_id', 'parties', ['contract_id'])
    
    # Create clauses table
    op.create_table(
        'clauses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('contract_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('contract_versions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('clause_number', sa.String(100), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('parent_clause_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clauses.id', ondelete='CASCADE'), nullable=True),
        sa.Column('order_index', sa.Integer, nullable=False),
        sa.Column('uuid_from_extractor', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_clauses_contract_id', 'clauses', ['contract_id'])
    op.create_index('ix_clauses_version_id', 'clauses', ['version_id'])
    op.create_index('ix_clauses_parent_clause_id', 'clauses', ['parent_clause_id'])
    op.create_index('ix_clauses_order_index', 'clauses', ['order_index'])


def downgrade() -> None:
    op.drop_table('clauses')
    op.drop_table('parties')
    op.drop_table('contract_versions')
    op.drop_table('contracts')
