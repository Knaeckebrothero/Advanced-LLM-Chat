"""
Common models used across the application.
"""
from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel


def _as_utc(value: datetime) -> datetime:
    """Naive times from the database are UTC; with the zone they are sent with a 'Z'."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# A time the API sends as UTC ("2026-11-03T21:40:05Z"). Without the zone, browsers would
# read the database's naive UTC times as their local time.
UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


class ErrorResponse(BaseModel):
    """
    Represents an error response model for handling error details.

    This class is used to encapsulate error information, typically to be
    used in API responses to provide a standard error structure.

    :ivar error: The error description message that provides details
                 about the nature of the error.
    :type error: str
    """
    error: str
