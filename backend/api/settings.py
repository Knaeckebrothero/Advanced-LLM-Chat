"""
Settings API endpoints.
"""
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from backend.models.settings import AppSettings, AppSettingsResponse
from backend.database import db
from backend.security.auth import get_current_user

router = APIRouter(prefix="/api", tags=["Settings"])


@router.get("/settings",
            response_model=AppSettingsResponse,
            summary="Get User Settings",
            description="Retrieve application settings for the current user",
            operation_id="getUserSettings")
async def get_settings(current_user: dict = Depends(get_current_user)):
    """
    Retrieve application settings for the current user.

    This endpoint handles retrieving user-specific application settings such as theme
    and language preferences. If the user is a guest, default settings along with the
    current timestamp are returned. If a regular user does not have any saved settings
    in the database, the system falls back to default configuration. For users with
    custom settings saved in the database, those settings are retrieved and returned,
    with the updated_at field converted to a Unix timestamp.

    :param current_user: Dictionary containing user authentication and role details
                        (e.g., user_id, is_guest). Provided through dependency injection.
    :type current_user: dict
    :return: An object containing the user's theme, language, and the last updated timestamp.
    :rtype: AppSettingsResponse
    """
    user_id = current_user["user_id"]

    if current_user.get("is_guest"):
        # Return default settings for guest users with current timestamp
        return AppSettingsResponse(
            theme="auto",
            language="en",
            lastUpdated=int(time.time())
        )

    settings = db.get_user_settings(user_id)

    if settings:
        # Convert datetime to Unix timestamp
        updated_at = settings['updated_at']
        if isinstance(updated_at, str):
            updated_at_dt = datetime.fromisoformat(updated_at)
        else:
            updated_at_dt = updated_at
        last_updated_ts = int(updated_at_dt.timestamp())

        return AppSettingsResponse(
            theme=settings['theme'],
            language=settings['language'],
            lastUpdated=last_updated_ts
        )
    else:
        # Fallback defaults if user has no settings yet
        return AppSettingsResponse(
            theme="auto",
            language="en",
            lastUpdated=int(time.time())
        )


@router.put("/settings",
            response_model=AppSettingsResponse,
            summary="Update User Settings",
            description="Update application settings for the current user",
            operation_id="updateUserSettings")
async def update_settings(new_settings: AppSettings, current_user: dict = Depends(get_current_user)):
    """
    Updates user settings in the database with new preferences and returns the updated settings.

    This endpoint is responsible for updating user-specific settings such as theme and language.
    It checks if the user is a guest and, if so, restricts access to saving settings. The database
    handles timestamp updates automatically. After updating or inserting the new settings, the
    function retrieves the updated settings along with the last modified timestamp, which is
    returned to the caller.

    :param new_settings: New settings to be saved for the user.
    :type new_settings: AppSettings
    :param current_user: Dictionary containing current user details, including their ID and permissions.
    :type current_user: dict
    :return: An object containing the updated theme, language, and the timestamp of the last modification.
    :rtype: AppSettingsResponse
    """
    user_id = current_user["user_id"]
    if current_user.get("is_guest"):
        raise HTTPException(status_code=403, detail="Guests cannot save settings.")

    # Upsert settings using CRUD method
    settings = db.upsert_user_settings(
        user_id=user_id,
        theme=new_settings.theme,
        language=new_settings.language
    )

    # Convert datetime to Unix timestamp
    try:
        updated_at = settings['updated_at']
        if isinstance(updated_at, str):
            updated_at_dt = datetime.fromisoformat(updated_at)
        else:
            updated_at_dt = updated_at
        last_updated_ts = int(updated_at_dt.timestamp())
    except (ValueError, TypeError):
        # Fallback to current time if parsing fails
        last_updated_ts = int(time.time())

    return AppSettingsResponse(
        theme=settings['theme'],
        language=settings['language'],
        lastUpdated=last_updated_ts
    )
