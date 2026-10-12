import enum
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    USER = "user"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.USER)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
