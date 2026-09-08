from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class DocumentCounter(Base):
    """Per-prefix, per-period running number behind human-readable document numbers."""

    __tablename__ = "document_counters"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, default=0)
