"""add users

Revision ID: b7e4a1c2d3f5
Revises: d9c208b5f3b7
Create Date: 2026-09-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e4a1c2d3f5'
down_revision: Union[str, Sequence[str], None] = 'd9c208b5f3b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('role', sa.Enum('ADMIN', 'USER', name='userrole'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    sa.Enum(name='userrole').drop(op.get_bind(), checkfirst=True)
