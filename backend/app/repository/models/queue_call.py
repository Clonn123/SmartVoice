from datetime import datetime
import enum
from sqlalchemy import Column, DateTime, String, Enum

from app.repository.models.base import Base


class StatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROCESS = "IN_PROCESS"
    FINISH = "FINISH"
    FAIL = "FAIL"


class TaskQueue(Base):
    __tablename__ = "task_queue"

    id = Column(String, primary_key=True)
    phone = Column(String, nullable=False)
    status = Column(Enum(StatusEnum), default=StatusEnum.PENDING, nullable=False)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
