"""Create synchronization run and item tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-25
"""
import alembic.op as op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql


revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')

    op.create_table(
        'sync_run',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('sync_type', sa.Text(), nullable=False),
        sa.Column('trigger', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('retry_of_id', sa.UUID(), nullable=True),
        sa.Column('total_items', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column(
            'succeeded_items',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column('failed_items', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column(
            'queued_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'partially_completed', 'failed')",
            name='ck_sync_run_status',
        ),
        sa.CheckConstraint(
            "trigger IN ('manual', 'scheduled', 'retry')",
            name='ck_sync_run_trigger',
        ),
        sa.CheckConstraint(
            'total_items >= 0 AND succeeded_items >= 0 AND failed_items >= 0',
            name='ck_sync_run_non_negative_counters',
        ),
        sa.ForeignKeyConstraint(
            ['retry_of_id'],
            ['sync_run.id'],
            name='fk_sync_run_retry_of_id_sync_run',
        ),
        sa.PrimaryKeyConstraint('id', name='pk_sync_run'),
    )
    op.create_index('ix_sync_run_queued_at', 'sync_run', [sa.text('queued_at DESC')])
    op.create_index(
        'uq_sync_run_active_type',
        'sync_run',
        ['sync_type'],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        'sync_item',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('external_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column(
            'source_payload',
            sqlalchemy.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            'destination_response',
            sqlalchemy.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed')",
            name='ck_sync_item_status',
        ),
        sa.CheckConstraint('attempts >= 0', name='ck_sync_item_non_negative_attempts'),
        sa.ForeignKeyConstraint(
            ['run_id'],
            ['sync_run.id'],
            name='fk_sync_item_run_id_sync_run',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name='pk_sync_item'),
        sa.UniqueConstraint('run_id', 'external_id', name='uq_sync_item_run_id'),
    )
    op.create_index('ix_sync_item_run_status', 'sync_item', ['run_id', 'status'])


def downgrade() -> None:
    pass
