import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class RentalStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Rental(Base):
    __tablename__ = "rentals"
    # Lab 7: GET /me/rentals filters by renter and sorts by newest first.
    __table_args__ = (Index("ix_rentals_renter_id_started_at", "renter_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    renter_id: Mapped[int] = mapped_column(ForeignKey("renters.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    start_station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
    end_station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[RentalStatus] = mapped_column(SAEnum(RentalStatus), default=RentalStatus.ACTIVE)
