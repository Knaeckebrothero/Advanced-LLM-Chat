"""
Common models used across the application.
"""
from pydantic import BaseModel


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
