from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Renter(Base):
    __tablename__ = "renters"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    license_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
