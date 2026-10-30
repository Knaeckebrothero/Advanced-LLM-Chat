"""
Model catalog API endpoints.

GET /api/models and GET /api/personas serve the model and persona pickers of
every user (guests only see what is available to guests). Everything under
/api/admin manages the catalog and is limited to admins (ADMIN_EMAILS).

Providers are read-only here: they come from the server's catalog file
(MODEL_CATALOG_FILE), and their API keys from environment variables, which no
response contains. Models and personas (the "agents" of the UI) are edited here.

The contract is in docs/model_catalog_api.md.
"""
import logging
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from backend.catalog import catalog_file, service
from backend.catalog.fetch import fetch_provider_models
from backend.catalog.resolver import ModelNotAvailable, get_model_config
from backend.catalog.service import CatalogError
from backend.llm import complete
from backend.models.catalog import (
    FetchModelsResponse,
    ImportResult,
    ModelCreate,
    ModelOut,
    ModelTestResult,
    ModelUpdate,
    PersonaCreate,
    PersonaOut,
    PersonaUpdate,
    ProviderOut,
    PublicModel,
    PublicPersona,
    ToolGroupStatus,
)
from backend.security.auth import get_current_user, require_admin
from backend.security.logging import crud_logger

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api", tags=["Catalog"])

ADMIN_ERRORS = {
    status.HTTP_403_FORBIDDEN: {"description": "Admin access required"},
}


def _http_error(error: CatalogError) -> HTTPException:
    """Turn a catalog error into an HTTP error with its status code."""
    return HTTPException(status_code=error.status_code, detail=str(error))


# =========================================================================
# Pickers (every user, guests filtered)
# =========================================================================

@router.get("/models",
            response_model=List[PublicModel],
            summary="List Models",
            description="Enabled catalog models of enabled providers that the current user may use",
            operation_id="listModels")
async def list_models(current_user: dict = Depends(get_current_user)):
    """
    Lists the models for the model picker, sorted by sort order, then name.

    Guests only see models available to guests. The list is empty when the
    catalog is empty; the environment model answers then.

    :param current_user: The authenticated user, injected via get_current_user.
    :type current_user: dict
    :return: The models the user may pick.
    :rtype: List[PublicModel]
    """
    models = service.public_models(current_user)
    logger.debug(f"Returning {len(models)} models for user_id {current_user['user_id']}")
    return models


@router.get("/personas",
            response_model=List[PublicPersona],
            summary="List Personas",
            description="Enabled personas that the current user may use",
            operation_id="listPersonas")
async def list_personas(current_user: dict = Depends(get_current_user)):
    """
    Lists the personas for the persona picker, sorted by sort order, then name.

    Guests only see personas available to guests.

    :param current_user: The authenticated user, injected via get_current_user.
    :type current_user: dict
    :return: The personas the user may pick.
    :rtype: List[PublicPersona]
    """
    personas = service.public_personas(current_user)
    logger.debug(f"Returning {len(personas)} personas for user_id {current_user['user_id']}")
    return personas


# =========================================================================
# Admin: providers
# =========================================================================

@router.get("/admin/providers",
            response_model=List[ProviderOut],
            responses=ADMIN_ERRORS,
            summary="List Providers",
            operation_id="adminListProviders")
async def admin_list_providers(admin: dict = Depends(require_admin)):
    """
    Lists all providers (API accounts) with their model counts, by name.

    Providers are defined in the server's catalog file; there are no endpoints
    to change them.

    :return: The providers; apiKeySet says whether the key variable is set.
    :rtype: List[ProviderOut]
    """
    return service.list_providers()


@router.post("/admin/providers/{provider_id}/fetch-models",
             response_model=FetchModelsResponse,
             responses={**ADMIN_ERRORS, status.HTTP_502_BAD_GATEWAY: {"description": "The provider's API call failed"}},
             summary="Fetch Provider Models",
             operation_id="adminFetchProviderModels")
async def admin_fetch_provider_models(provider_id: int, admin: dict = Depends(require_admin)):
    """
    Lists the models the provider offers (its GET /models), marking those
    already in the catalog.

    :param provider_id: The provider's ID.
    :type provider_id: int
    :return: The provider's models.
    :rtype: FetchModelsResponse
    :raises HTTPException: 404 if not found, 502 with the provider's message if the call fails.
    """
    try:
        return await fetch_provider_models(provider_id)
    except CatalogError as e:
        raise _http_error(e)


# =========================================================================
# Admin: models
# =========================================================================

@router.get("/admin/models",
            response_model=List[ModelOut],
            responses=ADMIN_ERRORS,
            summary="List Catalog Models",
            operation_id="adminListModels")
async def admin_list_models(admin: dict = Depends(require_admin)):
    """
    Lists all catalog models, including disabled ones, by sort order and name.

    :return: The models.
    :rtype: List[ModelOut]
    """
    return service.list_models()


@router.post("/admin/models",
             response_model=ModelOut,
             status_code=status.HTTP_201_CREATED,
             responses=ADMIN_ERRORS,
             summary="Create Catalog Model",
             operation_id="adminCreateModel")
async def admin_create_model(req: ModelCreate, admin: dict = Depends(require_admin)):
    """
    Creates a catalog model.

    :param req: The model.
    :type req: ModelCreate
    :return: The created model.
    :rtype: ModelOut
    :raises HTTPException: 400 if the provider does not exist or a field is invalid,
        409 if the provider already has a model with this display name.
    """
    try:
        model = service.create_model(req)
    except CatalogError as e:
        raise _http_error(e)
    crud_logger.info(f"Model created - id: {model.id}, name: {model.displayName}, "
                     f"provider: {model.providerName}, by user {admin['user_id']}")
    return model


@router.put("/admin/models/{model_id}",
            response_model=ModelOut,
            responses=ADMIN_ERRORS,
            summary="Update Catalog Model",
            operation_id="adminUpdateModel")
async def admin_update_model(model_id: int, req: ModelUpdate, admin: dict = Depends(require_admin)):
    """
    Updates the fields of a model that are sent; null clears optional fields.

    :param model_id: The model's ID.
    :type model_id: int
    :param req: The fields to change.
    :type req: ModelUpdate
    :return: The updated model.
    :rtype: ModelOut
    :raises HTTPException: 404 if not found, 400 for invalid fields, 409 if the name is taken.
    """
    try:
        model = service.update_model(model_id, req)
    except CatalogError as e:
        raise _http_error(e)
    crud_logger.info(f"Model updated - id: {model_id}, fields: {sorted(req.model_fields_set)}, "
                     f"by user {admin['user_id']}")
    return model


@router.delete("/admin/models/{model_id}",
               status_code=status.HTTP_204_NO_CONTENT,
               responses=ADMIN_ERRORS,
               summary="Delete Catalog Model",
               operation_id="adminDeleteModel")
async def admin_delete_model(model_id: int, admin: dict = Depends(require_admin)):
    """
    Deletes a catalog model. Conversations that used it fall back to the default model.

    :param model_id: The model's ID.
    :type model_id: int
    :raises HTTPException: 404 if not found.
    """
    try:
        service.delete_model(model_id)
    except CatalogError as e:
        raise _http_error(e)
    crud_logger.info(f"Model deleted - id: {model_id}, by user {admin['user_id']}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Prompt and output limit of the model test; thinking models need room to think first
MODEL_TEST_PROMPT = "Reply with one short sentence that says which model you are."
MODEL_TEST_MAX_OUTPUT_TOKENS = 4096


@router.post("/admin/models/{model_id}/test",
             response_model=ModelTestResult,
             responses=ADMIN_ERRORS,
             summary="Test Catalog Model",
             operation_id="adminTestModel")
async def admin_test_model(model_id: int, admin: dict = Depends(require_admin)):
    """
    Sends one short request to a catalog model, also when it or its provider is disabled.

    A failing call is reported in the result (ok=false with the provider's error
    message), not as an HTTP error.

    :param model_id: The model's ID.
    :type model_id: int
    :return: Whether the call worked, its latency and the reply or error.
    :rtype: ModelTestResult
    :raises HTTPException: 404 if the model doesn't exist.
    """
    try:
        config = get_model_config(model_id)
    except ModelNotAvailable as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    started = time.monotonic()
    try:
        reply, _ = await complete(
            config,
            [{"role": "user", "content": MODEL_TEST_PROMPT}],
            max_output_tokens=MODEL_TEST_MAX_OUTPUT_TOKENS
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - started) * 1000)
        crud_logger.info(f"Model test failed - id: {model_id}, by user {admin['user_id']}: {e}")
        return ModelTestResult(ok=False, latencyMs=latency_ms, error=str(e)[:500])

    latency_ms = int((time.monotonic() - started) * 1000)
    crud_logger.info(f"Model test ok - id: {model_id}, {latency_ms} ms, by user {admin['user_id']}")
    return ModelTestResult(ok=True, latencyMs=latency_ms, reply=reply.strip()[:500])


# =========================================================================
# Admin: personas
# =========================================================================

@router.get("/admin/personas",
            response_model=List[PersonaOut],
            responses=ADMIN_ERRORS,
            summary="List Catalog Personas",
            operation_id="adminListPersonas")
async def admin_list_personas(admin: dict = Depends(require_admin)):
    """
    Lists all personas, including disabled ones, by sort order and name.

    :return: The personas.
    :rtype: List[PersonaOut]
    """
    return service.list_personas()


@router.post("/admin/personas",
             response_model=PersonaOut,
             status_code=status.HTTP_201_CREATED,
             responses=ADMIN_ERRORS,
             summary="Create Persona",
             operation_id="adminCreatePersona")
async def admin_create_persona(req: PersonaCreate, admin: dict = Depends(require_admin)):
    """
    Creates a persona.

    :param req: The persona.
    :type req: PersonaCreate
    :return: The created persona.
    :rtype: PersonaOut
    :raises HTTPException: 400 if a variable is declared twice, 409 if the name is taken.
    """
    try:
        persona = service.create_persona(req)
    except CatalogError as e:
        raise _http_error(e)
    crud_logger.info(f"Persona created - id: {persona.id}, name: {persona.name}, by user {admin['user_id']}")
    return persona


@router.put("/admin/personas/{persona_id}",
            response_model=PersonaOut,
            responses=ADMIN_ERRORS,
            summary="Update Persona",
            operation_id="adminUpdatePersona")
async def admin_update_persona(persona_id: int, req: PersonaUpdate, admin: dict = Depends(require_admin)):
    """
    Updates the fields of a persona that are sent. tools: null selects every
    enabled tool, [] none.

    :param persona_id: The persona's ID.
    :type persona_id: int
    :param req: The fields to change.
    :type req: PersonaUpdate
    :return: The updated persona.
    :rtype: PersonaOut
    :raises HTTPException: 404 if not found, 400 for invalid fields, 409 if the name is taken.
    """
    try:
        persona = service.update_persona(persona_id, req)
    except CatalogError as e:
        raise _http_error(e)
    crud_logger.info(f"Persona updated - id: {persona_id}, fields: {sorted(req.model_fields_set)}, "
                     f"by user {admin['user_id']}")
    return persona


@router.delete("/admin/personas/{persona_id}",
               status_code=status.HTTP_204_NO_CONTENT,
               responses=ADMIN_ERRORS,
               summary="Delete Persona",
               operation_id="adminDeletePersona")
async def admin_delete_persona(persona_id: int, admin: dict = Depends(require_admin)):
    """
    Deletes a persona. Conversations that used it continue without it.

    :param persona_id: The persona's ID.
    :type persona_id: int
    :raises HTTPException: 404 if not found.
    """
    try:
        service.delete_persona(persona_id)
    except CatalogError as e:
        raise _http_error(e)
    crud_logger.info(f"Persona deleted - id: {persona_id}, by user {admin['user_id']}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =========================================================================
# Admin: tools
# =========================================================================

@router.get("/admin/tools",
            response_model=List[ToolGroupStatus],
            responses=ADMIN_ERRORS,
            summary="List Tool Groups",
            description="The tool groups a persona can select, with whether the server enables them",
            operation_id="adminListToolGroups")
async def admin_list_tool_groups(admin: dict = Depends(require_admin)):
    """
    Lists every tool group (files, web_search, knowledge_graph) and whether the
    server's configuration enables it. A persona that selects an unavailable
    group simply doesn't get its tools.

    :return: The tool groups; reason says why a group is unavailable.
    :rtype: List[ToolGroupStatus]
    """
    return service.list_tool_groups()


# =========================================================================
# Admin: catalog file
# =========================================================================

@router.get("/admin/catalog/export",
            responses=ADMIN_ERRORS,
            summary="Export Catalog",
            description="The whole catalog in the catalog file format (docs/model_catalog_api.md)",
            operation_id="adminExportCatalog")
async def admin_export_catalog(admin: dict = Depends(require_admin)):
    """
    Exports providers, models and personas as a catalog file, usable as
    MODEL_CATALOG_FILE. It contains no API keys, only their variable names.

    :return: The catalog file (JSON, offered as a download).
    :rtype: JSONResponse
    """
    content = catalog_file.export_catalog()
    crud_logger.info(f"Catalog exported by user {admin['user_id']}")
    headers = {"Content-Disposition": 'attachment; filename="model-catalog.json"'}
    return JSONResponse(content=jsonable_encoder(content), headers=headers)


@router.post("/admin/catalog/import",
             response_model=ImportResult,
             responses=ADMIN_ERRORS,
             summary="Import Catalog",
             description="Upserts the models and personas of a catalog file by natural key; "
                         "ignores providers and never deletes",
             operation_id="adminImportCatalog")
async def admin_import_catalog(
        data: Dict[str, Any] = Body(..., description="A catalog file (docs/model_catalog_api.md)"),
        admin: dict = Depends(require_admin)
):
    """
    Imports a catalog file: models by provider and display name, personas by
    name. Provider entries are ignored (providers come from the server's
    catalog file). Bad entries are reported in errors; the others are still
    imported.

    :param data: The catalog file.
    :type data: dict
    :return: Created and updated counts per section, and the errors.
    :rtype: ImportResult
    :raises HTTPException: 400 if the file itself is malformed (e.g. wrong version).
    """
    try:
        result = catalog_file.import_catalog(data)
    except CatalogError as e:
        raise _http_error(e)
    crud_logger.info(
        f"Catalog imported by user {admin['user_id']} - models {result.models.created}+{result.models.updated}, "
        f"personas {result.personas.created}+{result.personas.updated} (created+updated), "
        f"{len(result.errors)} error(s)"
    )
    return result
