import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class RentalStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Rental(Base):
    __tablename__ = "rentals"

    id: Mapped[int] = mapped_column(primary_key=True)
    renter_id: Mapped[int] = mapped_column(ForeignKey("renters.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    start_station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
    end_station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[RentalStatus] = mapped_column(SAEnum(RentalStatus), default=RentalStatus.ACTIVE)
