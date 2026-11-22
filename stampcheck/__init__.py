"""Check whether a human approval step still filters anything, or has become a rubber stamp."""
from .config import NAME, VERSION as __version__
from .record import record_review, review

__all__ = ["NAME", "record_review", "review", "__version__"]
