from datetime import datetime
import uuid
from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, Uuid, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','preparing','running','completed','failed','awaiting_selection')", name="job_status"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="job_progress"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(200))
    owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_bytes: Mapped[int] = mapped_column(BigInteger)
    model_id: Mapped[str] = mapped_column(String(64))
    model_label: Mapped[str] = mapped_column(String(160))
    model_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(500), default="Đang chờ xử lý")
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(200))
    owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    total_bytes: Mapped[int] = mapped_column(BigInteger)
    offset: Mapped[int] = mapped_column(BigInteger, default=0)
    model_id: Mapped[str] = mapped_column(String(64))
    model_label: Mapped[str] = mapped_column(String(160))
    model_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="uploading")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
