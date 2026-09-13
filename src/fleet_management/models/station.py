from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(200))
    capacity: Mapped[int] = mapped_column()
