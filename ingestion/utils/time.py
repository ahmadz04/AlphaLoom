from datetime import datetime, timezone
from dateutil import parser

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def to_utc(dt_like: str) -> datetime:
    """Parse any ISO (with offset) to timezone-aware UTC datetime."""
    dt = parser.isoparse(dt_like)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
