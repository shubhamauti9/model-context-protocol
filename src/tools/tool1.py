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
from src.config import API_KEY
from utils.helpers import Helpers
from session.manager import SessionManager
from utils.request import CustomRequest
from toon_format import encode

"""
A service class to handle tool.
"""
class Tool1Service:
    """
    Implements the example of tool
    """

    mcp = Server._instance.mcp if Server._instance is not None else FastMCP(name="mask-mcp")
    
    _instance = None
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Tool1Service, cls).__new__(cls)
            logger.info("Tool 1 Service instance created")
        return cls._instance
    
    """
    Initializes the Tool1 Service with necessary dependencies.

    Args:
        helpers_util (helpers.helpers): An instance of the helpers utility class.
        session_manager (SessionManager): An instance of the session manager.
    """
    def __init__(
        self, helpers: Helpers, session_manager: SessionManager
    ):
        self.api_key = API_KEY
        self.helpers = helpers
        self.session_manager = session_manager

    """
    example tool 1.
    """
    def tool_1(
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
            return encode({"status": "error", "message": "Session is Expired. Please login again."})

        #make the request to the API
        custom_request = CustomRequest(
            api_key=self.api_key,
            access_token=accessToken,
            state=mcp_session_id,
            debug=False
        )   
        response = custom_request._request(
            route="api.tool1",
            method="GET",
            parameters={}
        )
        if response.status_code != 200:
            session_logger(
                mcp_session_id,
                "error",
                "Failed to call tool 1 API",
                "tool"
            )
            return encode({"status": "error", "message": "Failed to call tool 1 API"})
        #return the response in toon format
        return encode(response.json())