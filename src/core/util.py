"""Small shared helpers used across agents."""

from datetime import datetime
from typing import Optional

# Olist CSV timestamps look like "2017-12-13 13:45:24".
_TS_FMT = "%Y-%m-%d %H:%M:%S"


def parse_ts(value) -> Optional[datetime]:
    """Parse an Olist timestamp string into a datetime.

    Returns None for blanks / NaN / NaT — common on canceled or undelivered
    orders (README §2). Timestamps are compared as-is, no timezone conversion.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "nat", "none", "null"):
        return None
    return datetime.strptime(s[:19], _TS_FMT)
