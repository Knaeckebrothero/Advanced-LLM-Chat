"""
API documentation endpoints (OpenAPI, Swagger UI).
"""
import logging
from fastapi import Request, Response, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

logger = logging.getLogger(__name__)


def create_docs_routes(app):
    """
    Register documentation routes with the FastAPI app.

    :param app: The FastAPI application instance
    """
    logger.debug("Registering documentation routes")

    @app.get(app.openapi_url, include_in_schema=False)
    async def custom_openapi():
        """
        Generates a custom OpenAPI schema for the FastAPI app.

        This function overrides the existing OpenAPI schema generation for the FastAPI
        application. It utilizes the `get_openapi` utility to create a custom schema
        using the app's metadata such as title, version, description, and registered
        routes.

        :return: The custom-generated OpenAPI schema as a dictionary.
        :rtype: dict
        """
        logger.debug("OpenAPI schema requested")
        return get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

    @app.get("/api/docs", include_in_schema=False)
    async def custom_swagger_ui_html(req: Request):
        """
        Generates and serves a custom Swagger UI HTML interface for the API.

        Provides a user interface to explore the API endpoints and their
        documentation using the Swagger UI. This view is accessible at '/api/docs'
        but is excluded from the schema.

        :param req: The HTTP request object containing metadata about the
            incoming request and connection-specific data.
        :type req: Request
        :return: The HTML response content for the Swagger UI.
        :rtype: HTMLResponse
        """
        logger.debug("Swagger UI requested")
        root_path = req.scope.get("root_path", "").rstrip("/")
        openapi_url = root_path + app.openapi_url
        return get_swagger_ui_html(
            openapi_url=openapi_url,
            title=app.title + " - Swagger UI"
        )

    @app.options("/{rest_of_path:path}")
    async def preflight_handler(rest_of_path: str):
        """
        Handles HTTP OPTIONS requests to support CORS preflight actions.

        This function is used to respond to preflight requests with an HTTP status
        code of 200 to indicate that the request is allowed. CORS (Cross-Origin
        Resource Sharing) preflight requests are triggered by clients (browsers)
        to verify permissions between the requesting domain and the resource's
        domain.

        :param rest_of_path: The variable path segment of the request route.
        :type rest_of_path: str
        :return: A response with HTTP status code 200 indicating successful preflight handling.
        :rtype: Response
        """
        return Response(status_code=status.HTTP_200_OK)
