"""
Settings API endpoints.
"""
import logging
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from backend.models.settings import AppSettings, AppSettingsResponse
from backend.catalog.service import CatalogError, check_model_choice
from backend.database import db
from backend.database.db import UNSET
from backend.security.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Settings"])

# Settings fields that an update may leave out to keep the stored value, by database column
OPTIONAL_FIELDS = {
    "background": "background",
    "backgroundDim": "background_dim",
    "backgroundBlur": "background_blur",
}


def _appearance(settings: dict) -> dict:
    """The background fields of a user_settings row, with defaults for rows from before they existed."""
    defaults = AppSettings.model_fields
    return {
        field: settings.get(column) if settings.get(column) is not None else defaults[field].default
        for field, column in OPTIONAL_FIELDS.items()
    }


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
    logger.debug(f"Get settings for user_id: {user_id}")

    if current_user.get("is_guest"):
        # Default settings for guests; lastUpdated 0 so they never override settings stored in the browser
        logger.debug("Guest user - returning default settings")
        return AppSettingsResponse(
            theme="auto",
            language="en",
            lastUpdated=0
        )

    settings = db.get_user_settings(user_id)

    if settings:
        logger.debug(f"Found settings for user_id {user_id}: theme={settings['theme']}, language={settings['language']}")
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
            defaultModelId=settings.get('default_model_id'),
            **_appearance(settings),
            lastUpdated=last_updated_ts
        )
    else:
        # Fallback defaults if user has no settings yet (lastUpdated 0: older than anything stored)
        logger.debug(f"No settings found for user_id {user_id}, returning defaults")
        return AppSettingsResponse(
            theme="auto",
            language="en",
            lastUpdated=0
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
    logger.debug(f"Update settings for user_id: {user_id} - theme: {new_settings.theme}, language: {new_settings.language}")

    if current_user.get("is_guest"):
        logger.warning(f"Guest user attempted to save settings")
        raise HTTPException(status_code=403, detail="Guests cannot save settings.")

    # Default model: left out = keep the stored one, null = clear it
    default_model_id = UNSET
    if "defaultModelId" in new_settings.model_fields_set:
        default_model_id = new_settings.defaultModelId
        try:
            check_model_choice(current_user, default_model_id)
        except CatalogError as e:
            logger.warning(f"Rejected default model {default_model_id} for user_id {user_id}: {e}")
            raise HTTPException(status_code=e.status_code, detail=str(e))

    # Background settings: left out = keep the stored values
    appearance = {
        column: getattr(new_settings, field)
        for field, column in OPTIONAL_FIELDS.items()
        if field in new_settings.model_fields_set
    }

    # Upsert settings using CRUD method
    settings = db.upsert_user_settings(
        user_id=user_id,
        theme=new_settings.theme,
        language=new_settings.language,
        default_model_id=default_model_id,
        **appearance
    )

    logger.info(f"Settings updated for user_id {user_id}: theme={new_settings.theme}, language={new_settings.language}, "
                f"default_model_id={settings.get('default_model_id')}")

    # Convert datetime to Unix timestamp
    try:
        updated_at = settings['updated_at']
        if isinstance(updated_at, str):
            updated_at_dt = datetime.fromisoformat(updated_at)
        else:
            updated_at_dt = updated_at
        last_updated_ts = int(updated_at_dt.timestamp())
    except (ValueError, TypeError) as e:
        # Fallback to current time if parsing fails
        logger.warning(f"Failed to parse updated_at timestamp: {e}, using current time")
        last_updated_ts = int(time.time())

    return AppSettingsResponse(
        theme=settings['theme'],
        language=settings['language'],
        defaultModelId=settings.get('default_model_id'),
        **_appearance(settings),
        lastUpdated=last_updated_ts
    )
