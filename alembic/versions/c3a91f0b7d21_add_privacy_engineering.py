"""add privacy engineering tables (consent, activity, audit, marketing, analytics)

Revision ID: c3a91f0b7d21
Revises: b7e4a1c2d3f5
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a91f0b7d21'
down_revision: Union[str, Sequence[str], None] = 'b7e4a1c2d3f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PURPOSES = ('MARKETING_EMAIL', 'OPTIONAL_ANALYTICS', 'PERSONALIZATION')


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=30)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('phone', sa.String(length=32), nullable=True))
    op.add_column('users', sa.Column('anonymized_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('renters', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_unique_constraint('uq_renters_user_id', 'renters', ['user_id'])
    op.create_foreign_key('fk_renters_user_id_users', 'renters', 'users', ['user_id'], ['id'])

    op.create_table('user_consents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('purpose', _enum('consentpurpose', *PURPOSES), nullable=False),
    sa.Column('status', _enum('consentstatus', 'GRANTED', 'WITHDRAWN'), nullable=False),
    sa.Column('policy_version', sa.String(length=20), nullable=False),
    sa.Column('granted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source', sa.String(length=50), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'purpose', name='uq_user_consents_user_purpose')
    )
    op.create_index(op.f('ix_user_consents_user_id'), 'user_consents', ['user_id'], unique=False)

    op.create_table('consent_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('purpose', _enum('consentpurpose', *PURPOSES), nullable=False),
    sa.Column('action', _enum('consentaction', 'GRANT', 'REVOKE'), nullable=False),
    sa.Column('policy_version', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=50), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consent_history_user_id'), 'consent_history', ['user_id'], unique=False)

    op.create_table('user_activity',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_activity_user_id'), 'user_activity', ['user_id'], unique=False)

    op.create_table('audit_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('subject_id', sa.Integer(), nullable=True),
    sa.Column('result', sa.String(length=64), nullable=False),
    sa.Column('correlation_id', sa.String(length=64), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_events_event_type'), 'audit_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_audit_events_subject_id'), 'audit_events', ['subject_id'], unique=False)

    op.create_table('marketing_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('campaign', sa.String(length=64), nullable=False),
    sa.Column('status', _enum('marketingstatus', 'QUEUED', 'SENT', 'SKIPPED'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_marketing_messages_user_id'), 'marketing_messages', ['user_id'], unique=False)

    op.create_table('analytics_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('event_name', sa.String(length=64), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analytics_events_user_id'), 'analytics_events', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_analytics_events_user_id'), table_name='analytics_events')
    op.drop_table('analytics_events')
    op.drop_index(op.f('ix_marketing_messages_user_id'), table_name='marketing_messages')
    op.drop_table('marketing_messages')
    op.drop_index(op.f('ix_audit_events_subject_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_event_type'), table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index(op.f('ix_user_activity_user_id'), table_name='user_activity')
    op.drop_table('user_activity')
    op.drop_index(op.f('ix_consent_history_user_id'), table_name='consent_history')
    op.drop_table('consent_history')
    op.drop_index(op.f('ix_user_consents_user_id'), table_name='user_consents')
    op.drop_table('user_consents')
    op.drop_constraint('fk_renters_user_id_users', 'renters', type_='foreignkey')
    op.drop_constraint('uq_renters_user_id', 'renters', type_='unique')
    op.drop_column('renters', 'user_id')
    op.drop_column('users', 'anonymized_at')
    op.drop_column('users', 'phone')
