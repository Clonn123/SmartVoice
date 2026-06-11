import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship

from app.repository.models.base import Base


class CallTaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CallAttemptResult(str, enum.Enum):
    SUCCESS = "SUCCESS"
    BOT_FINISHED = "BOT_FINISHED"
    ANSWERED = "ANSWERED"

    NO_ANSWER = "NO_ANSWER"
    BUSY = "BUSY"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    ERROR = "ERROR"


class CallTask(Base):
    __tablename__ = "call_tasks"

    id = Column(Integer, primary_key=True, index=True)

    phone = Column(String(32), nullable=False, index=True)

    status = Column(String(32), nullable=False, default=CallTaskStatus.PENDING)

    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)

    next_attempt_at = Column(DateTime, nullable=True)

    prompt = Column(Text, nullable=True)
    scenario = Column(String(128), nullable=True)
    target_payload = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    last_result = Column(String(64), nullable=True)
    completed = Column(Boolean, nullable=False, default=False)

    celery_task_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    attempts_history = relationship(
        "CallAttempt",
        back_populates="call_task",
        cascade="all, delete-orphan",
    )


class CallAttempt(Base):
    __tablename__ = "call_attempts"

    id = Column(Integer, primary_key=True, index=True)

    call_task_id = Column(
        Integer, ForeignKey("call_tasks.id"), nullable=False, index=True
    )

    attempt_number = Column(Integer, nullable=False)

    status = Column(String(32), nullable=False, default="RUNNING")
    result = Column(String(64), nullable=True)

    celery_task_id = Column(String(255), nullable=True)

    channel_id = Column(String(255), nullable=True)

    answered = Column(Boolean, nullable=False, default=False)
    bot_finished = Column(Boolean, nullable=False, default=False)

    hangup_cause = Column(Integer, nullable=True)
    hangup_text = Column(String(255), nullable=True)

    error = Column(Text, nullable=True)

    dialog_json = Column(JSON, nullable=True)
    recording_path = Column(String(512), nullable=True)

    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    call_task = relationship("CallTask", back_populates="attempts_history")
