from typing import Optional, Any
from fastmcp import Context, FastMCP
import uvicorn

from config import (
    HOST,
    PORT
)
from conn import redis_config
from log.logger import logger
from middleware.middleware import CustomMiddleware
from src.tools.tool1 import Tool1Service
from src.utils.constants import TOOL_1_DESCRIPTION
from utils.helpers import Helpers
from session.manager import SessionManager
from server.server import Server

logger.info("Initializing FastMCP for MCP server")
mcp = FastMCP(name="mcp")

"""
SERVER STARTUP LOGIC
"""
if __name__ == "__main__":

    logger.info("Initializing Custom Middleware for MCP server")
    custom_middleware=CustomMiddleware(mcp)

    server = Server._instance

    logger.info("Initializing Server for MCP server")
    server = Server(custom_middleware, mcp)

    logger.info("Creating Starlette application instance for MCP server")
    starlette_app = server.create_app()

    try:
        redis_config.redis_client.ping()
    except Exception as e:
        logger.error(f"Error while redis connection with error {e} ")
        raise e

    helpers = Helpers._instance
    if helpers is None:
        logger.info("Initializing Helpers for MCP server")
        helpers = Helpers()
    
    session_manager = SessionManager._instance
    if session_manager is None:
        logger.info("Initializing Session Manager for MCP server")
        session_manager = SessionManager()
    
    """
    Initializes the tools which are used in the MCP server
    """
    
    logger.info("Initializing Tool 1 Service for MCP server")
    tool_1_service = Tool1Service(
        helpers if helpers is not None else Helpers(),
        session_manager if session_manager is not None else SessionManager()
    )
    
    @mcp.tool(
        name="Tool_1",
        description=TOOL_1_DESCRIPTION,
        annotations={
            "ctx": {"type": "object", "description": "The context object provided by fastmcp to manage session and activity."},
            "returns": {"type": "dict"}
        }
    )
    async def tool_1(ctx: Context):
        return tool_1_service.tool_1(ctx)

    try:    
        logger.info(f"Starting MCP server on http://{HOST}:{PORT}")
        uvicorn.run(starlette_app, host=HOST, port=int(PORT))
    finally:
        logger.error("error : MCP server stopped")