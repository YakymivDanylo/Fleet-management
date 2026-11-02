"""add performance indexes

Revision ID: e1f4a7c9b2d6
Revises: c3a91f0b7d21
Create Date: 2026-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e1f4a7c9b2d6'
down_revision: Union[str, Sequence[str], None] = 'c3a91f0b7d21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_vehicles_station_id_status', 'vehicles', ['station_id', 'status'])
    op.create_index('ix_rentals_renter_id_started_at', 'rentals', ['renter_id', 'started_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_rentals_renter_id_started_at', table_name='rentals')
    op.drop_index('ix_vehicles_station_id_status', table_name='vehicles')
