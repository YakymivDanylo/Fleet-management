import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class VehicleStatus(enum.StrEnum):
    AVAILABLE = "available"
    RENTED = "rented"
    MAINTENANCE = "maintenance"


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    license_plate: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[VehicleStatus] = mapped_column(
        SAEnum(VehicleStatus), default=VehicleStatus.AVAILABLE
    )
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
