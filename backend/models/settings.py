"""
Settings-related models.
"""
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
    """
    theme: str
    language: str


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
