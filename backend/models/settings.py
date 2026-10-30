"""
Settings-related models.
"""
from typing import Optional
from pydantic import BaseModel


class AppSettings(BaseModel):
    """
    Manages application settings such as theme and language preferences.

    Provides storage for user-specified application configurations, enabling
    customization of the application behavior and appearance.

    :ivar theme: The theme preference of the user.
    :type theme: str
    :ivar language: The language preference of the user.
    :type language: str
    :ivar defaultModelId: The catalog model for new conversations; None means the
        first catalog model (or the environment model). Left out in an update,
        the stored value is kept.
    :type defaultModelId: Optional[int]
    """
    theme: str
    language: str
    defaultModelId: Optional[int] = None


class AppSettingsResponse(AppSettings):
    """
    Represents the response format for application settings, extending the
    base application settings functionality.

    This class incorporates additional metadata regarding the last update time
    of the settings, stored as a Unix timestamp.

    :ivar lastUpdated: Indicates the Unix timestamp of the last update to the
        application settings.
    :type lastUpdated: int
    """
    lastUpdated: int  # Unix timestamp
