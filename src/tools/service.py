from typing import Optional
from requests.exceptions import HTTPError
from fastmcp import Context, FastMCP
from mcp.server.streamable_http import MCP_SESSION_ID_HEADER
from exception.error import Error
from log.logger import (
    logger,
    session_logger
)
from server.server import Server
from utils.helpers import Helpers
from session.manager import SessionManager
from utils.request import CustomRequest

"""
A service class to handle tool.
"""
class Service:
    """
    Implements the example of tool
    """

    mcp = Server._instance.mcp if Server._instance is not None else FastMCP(name="mask-mcp")
    
    _instance = None
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Service, cls).__new__(cls)
            logger.info("Service instance created")
        return cls._instance
    
    """
    Initializes the FundsService with necessary dependencies.

    Args:
        helpers_util (helpers.helpers): An instance of the helpers utility class.
        session_manager (SessionManager): An instance of the session manager.
    """
    def __init__(
        self, helpers: Helpers, session_manager: SessionManager
    ):
        self.helpers = helpers
        self.session_manager = session_manager

    """
    example tool.
    """
    def service(
        self, ctx: Context
    ) -> dict:
        request = ctx.request_context.request

        mcp_session_id = request.headers.get(MCP_SESSION_ID_HEADER)

        is_valid_session, accessToken = self.helpers.isValid(mcp_session_id)

        if not is_valid_session:
            session_logger(
                mcp_session_id,
                "error",
                "Session is Expired. Please login again. for session id",
                "tool"
            )
            return {"status": "error", "message": "Session is Expired. Please login again."}

        #further tool execution ex. api call or calculation or specific process