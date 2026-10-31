"""
Settings-related models.
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field

# Chat backgrounds: none, the two built-in images, or an image kept in the user's browser
Background = Literal["none", "aurora", "ridges", "custom"]

# Guided: editing your message answers it again. Manual: edit and insert any message, nothing is generated
EditingMode = Literal["guided", "manual"]


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
    :ivar background: The chat background. 'custom' is an image stored only in
        the browser, so other devices show no image. Left out in an update, the
        stored value is kept (as for the two fields below).
    :type background: Background
    :ivar backgroundDim: How much the theme background color covers the image, 0-80 %.
    :type backgroundDim: int
    :ivar backgroundBlur: Blur of the background image, 0-20 px.
    :type backgroundBlur: int
    :ivar editingMode: 'guided' or 'manual' (see EditingMode). Left out in an
        update, the stored value is kept.
    :type editingMode: EditingMode
    """
    theme: str
    language: str
    defaultModelId: Optional[int] = None
    background: Background = "none"
    backgroundDim: int = Field(25, ge=0, le=80)
    backgroundBlur: int = Field(0, ge=0, le=20)
    editingMode: EditingMode = "guided"


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
