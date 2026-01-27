from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from middleware.middleware import CustomMiddleware
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.middleware.cors import CORSMiddleware

from auth.oauth import MCPOAuthEndpoints
from auth.token import MCPTokenService
from session.manager import SessionManager

from log.logger import logger
from config import (
    AUTH_SERVER_BASE_URL,
    ISSUER,
    RESOURCE
)
from exception.error import Error

"""
A service class responsible for initializing and configuring the main Starlette application,
including FastMCP integration, custom middleware, routes, and lifespan management.
It follows the Singleton design pattern to ensure only one application instance exists.
"""
class Server:
    """
    Implements the Singleton design pattern for the Server class.

    This method is implicitly called before __init__() when a new instance
    of Server is requested. It ensures that only one instance of
    the Server class is created throughout the application's lifecycle.

    If an instance of Server does not already exist (i.e., _instance is None),
    it proceeds to create a new instance:
    1. It calls the `__new__` method of the superclass (typically `object` for a
       base class) to allocate memory and create the actual instance.
    2. The newly created instance is then assigned to the class-level attribute
       `cls._instance`, effectively storing the single instance.
    3. A flag `_initialized` is set to `False` to indicate that `__init__` needs
       to be run for this new instance.
    4. A log message is recorded indicating the creation of the instance.

    If an instance of Server already exists (i.e., `cls._instance` is not None),
    this method simply returns the existing instance stored in `cls._instance`,
    thereby preventing the creation of duplicate instances.

    Returns:
        Server: The singleton instance of the Server class.
    """
    _instance = None
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Server, cls).__new__(cls)
            logger.info("Server instance created.")
        return cls._instance

    """
    Initializes the Server Service with necessary dependencies.
    This method will only execute its core initialization logic once,
    even if the Server class is instantiated multiple times
    due to the Singleton pattern.

    Args:
        custom_middleware (CustomMiddleware): An instance of the custom middleware.
    """
    def __init__(self, custom_middleware: CustomMiddleware, mcp: FastMCP):
        self.middleware = custom_middleware
        self.mcp = mcp
        """
        Initialize OAuth components
        """
        self.session_manager = SessionManager()
        self.token_service = MCPTokenService()
        self.oauth_endpoints = MCPOAuthEndpoints(
            token_service=self.token_service,
            session_manager=self.session_manager
        )
        logger.info("OAuth components initialized")

    """
    Context manager for the application's lifespan
    This context manager will be executed by Starlette on startup and shutdown
    It explicitly runs the lifespan of the mounted mcp via the session manager
    """
    @asynccontextmanager
    async def _lifespan_context(self, app: Starlette) -> AsyncIterator[None]:
        logger.info("Entering application lifespan context.")
        try:
            async with self.middleware.session_manager.run():
                logger.info("Application started with StreamableHTTP session manager!")
                yield
        finally:
            raise Error("Application shutting down", 500)
    
    """
    Configures the routes and mounts static files for the Starlette application
    This method should be called after `self.starlette_app` is initialized
    """
    def _configure_routes(self, starlette_app: Starlette):
        """
        Mount MCP's ASGI app via the custom middleware handler
        """
        starlette_app.mount(
            "/mcp",self.middleware.handle_streamable_http
        )
        logger.info("Configured and mounted the streamable http application at /mcp")
        
        """
        Configure /http endpoint for OAuth Bearer token authentication
        Handles both GET (SSE handshake) and POST (MCP messages)
        CRITICAL: Use add_route (not mount) to avoid 307 redirects
        """
        starlette_app.add_route(
            "/http",
            self.middleware.handle_http_request,
            methods=["GET", "POST", "OPTIONS"]
        )
        logger.info("Configured /http endpoint for OAuth authentication (GET, POST)")
        
        """
        Add the redirect route for OAuth callback
        """
        starlette_app.add_route(
            "/redirect",
            self.middleware.handle_redirect
        )
        logger.info("Configured and mounted the redirect handler at /redirect")

        """
        OAuth Authorization Server Metadata (RFC8414)
        """
        starlette_app.add_route(
            "/.well-known/oauth-authorization-server",
            self._authorization_server_metadata
        )
        
        """
        Protected Resource Metadata (RFC9728)
        """
        starlette_app.add_route(
            "/.well-known/oauth-protected-resource",
            self._protected_resource_metadata
        )
        
        """
        OAuth endpoints
        """
        """
        Authorize endpoint
        """
        starlette_app.add_route(
            "/authorize",
            self.oauth_endpoints.authorization_endpoint
        )
        """
        Token Verification endpoint
        """
        starlette_app.add_route(
            "/token",
            self.oauth_endpoints.token_endpoint,
            methods=["POST"]
        )
        """
        dynamic client Registration --- not needed
        """
        starlette_app.add_route(
            "/register",
            self.oauth_endpoints._registration_not_supported,
            methods=["POST", "GET"]
        )
        logger.info("Configured /register endpoint (returns 501 - implicit registration)")

        """
        Add Route to conect sse
        """
        starlette_app.add_route("/sse", self.middleware.handle_sse)
        logger.info("Configured and mounted the handle sse endpoint to connect at /sse")
        """
        Mount handle post messages to sse connection
        """
        starlette_app.mount("/messages",  self.middleware.handle_sse_message)
        logger.info("Configured and mounted the handling post messages at /messages")

        """
        Mount health check status endpoint
        """
        starlette_app.add_route("/", self.middleware.health_check)
        logger.info("Configured and mounted the health check endpoint at /")

    """
    RFC8414: Authorization Server Metadata
    """
    async def _authorization_server_metadata(
        self, request: Request
    ) -> JSONResponse:
        return JSONResponse({
            "issuer": ISSUER,
            "authorization_endpoint": f"{AUTH_SERVER_BASE_URL}/authorize",
            "token_endpoint": f"{AUTH_SERVER_BASE_URL}/token",
            "registration_endpoint": f"{AUTH_SERVER_BASE_URL}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": [], #scope of mcp
            "service_documentation": AUTH_SERVER_BASE_URL,
            "registration_policy": "implicit"
        })

    """
    RFC9728: Protected Resource Metadata
    """
    async def _protected_resource_metadata(
        self, request: Request
    ) -> JSONResponse:
        return JSONResponse({
            "resource": RESOURCE,
            "authorization_servers": [AUTH_SERVER_BASE_URL],
            "bearer_methods_supported": ["header"],
            "resource_documentation": AUTH_SERVER_BASE_URL
        })

    """
    Creates and configures the Starlette application instance.
    This method ensures the application is created only once and
    its routes and lifespan are properly set up.

    Returns:
        Starlette: The configured Starlette application instance.
    """
    def create_app(self) -> Starlette:
        logger.info("Creating Starlette application instance")
        starlette_app = Starlette(
            debug=True,
            lifespan=self._lifespan_context  # type: ignore
        )
        logger.info("Adding CORS middleware BEFORE configuring routes")
        starlette_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["WWW-Authenticate"]
        )
        logger.info("Configuring routes for Starlette application instance")
        self._configure_routes(starlette_app)
        logger.info("Starlette application instance created and configured successfully.")
        return starlette_app