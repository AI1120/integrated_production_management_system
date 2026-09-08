"""Human-readable document numbers: WO-2609-0001, NCR-2609-0003, ..."""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models.counter import DocumentCounter


def next_number(db: Session, prefix: str, width: int = 4) -> str:
    """Reserve and format the next number for ``prefix`` in the current YYMM period.

    The counter row is locked by the surrounding transaction, so concurrent
    callers cannot be handed the same number.
    """
    period = datetime.now().strftime("%y%m")
    key = f"{prefix}-{period}"

    counter = db.get(DocumentCounter, key, with_for_update=False)
    if counter is None:
        counter = DocumentCounter(key=key, last_value=0)
        db.add(counter)
    counter.last_value += 1
    db.flush()
    return f"{prefix}-{period}-{counter.last_value:0{width}d}"
