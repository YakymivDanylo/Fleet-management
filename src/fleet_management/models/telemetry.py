from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class TelemetryReading(Base):
    __tablename__ = "telemetry_readings"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "recorded_at", name="uq_telemetry_vehicle_recorded_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[float]
    longitude: Mapped[float]
    fuel_level: Mapped[float]
    is_locked: Mapped[bool]
