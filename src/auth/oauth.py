from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from typing import Optional, Dict
import secrets
import uuid
import json
import hashlib
import base64
from urllib.parse import urlparse

from auth.token import MCPTokenService
from session.manager import SessionManager
from config import (
    SESSION_VALIDITY_SECS,
    AUTH_CODE_KEY_PREFIX
)
from conn.redis_config import redis_client
from log.logger import logger

"""
Simplified OAuth 2.1 endpoints for MCP server
    
Key Design:
    - OAuth creates session and issues token IMMEDIATELY
    - Session has no broker credentials yet
    - User calls Login tool later when they need broker features
"""
class MCPOAuthEndpoints:
    
    """
    constructor for oauth services endpoint
    """
    def __init__(
        self, 
        token_service: MCPTokenService, 
        session_manager: SessionManager
    ):
        self.token_service = token_service
        self.session_manager = session_manager

    """
    Simplified authorization - creates session and returns code immediately.
    """
    async def authorization_endpoint(
        self, request: Request
    ) -> RedirectResponse:
        """
        Extract OAuth parameters
        """
        redirect_uri = request.query_params.get("redirect_uri")

        state = request.query_params.get("state")

        code_challenge = request.query_params.get("code_challenge")

        code_challenge_method = request.query_params.get("code_challenge_method", "S256")

        scope = request.query_params.get("scope", "read:portfolio read:trades")
        
        """
        Validate redirect_uri
        """
        if not redirect_uri or not self._is_valid_redirect_uri(redirect_uri):
            return JSONResponse(
                { 
                    "error": "invalid_request", 
                    "error_description": "Invalid redirect_uri"
                },
                status_code=400
            )
        
        """
        Create session (empty, no broker login)
        """
        session_id = uuid.uuid4().hex
        self.session_manager.generateById(session_id=session_id)
        logger.info(f"OAuth: Created session {session_id}")
        
        """
        Generate authorization code immediately
        """
        auth_code = secrets.token_urlsafe(32)
        
        """
        Store code data for token exchange
        """
        self._store_authorization_code(
            auth_code, 
            {
                "session_id": session_id,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "scope": scope,
                "redirect_uri": redirect_uri
            }
        )
        
        """
        Redirect back to client immediately
        """
        callback_url = f"{redirect_uri}?code={auth_code}&state={state}"
        logger.info(f"Redirecting to {redirect_uri}")
        
        return RedirectResponse(callback_url)

    """
    Exchange authorization code for JWT Bearer token.
    Token contains session_id with no broker credentials yet.
    """
    async def token_endpoint(
        self, request: Request
    ) -> JSONResponse:
        """
        fetch form data from request
        """
        form_data = await request.form()
        
        code = form_data.get("code")
        redirect_uri = form_data.get("redirect_uri")
        code_verifier = form_data.get("code_verifier")
        grant_type = form_data.get("grant_type")
        
        """
        Validate grant type
        """
        if grant_type != "authorization_code":
            return JSONResponse(
                {"error": "unsupported_grant_type"},
                status_code=400
            )
        
        """
        Retrieve code data
        """
        code_data = self._retrieve_authorization_code(code)
        if not code_data:
            return JSONResponse(
                {
                    "error": "invalid_grant", 
                    "error_description": "Invalid or expired code"
                },
                status_code=400
            )
        
        """
        Validate PKCE
        """
        if not self._validate_pkce(code_verifier, code_data.get("code_challenge")):
            return JSONResponse(
                {
                    "error": "invalid_grant", 
                    "error_description": "PKCE validation failed"
                },
                status_code=400
            )
        
        """
        Validate redirect_uri
        """
        if redirect_uri != code_data["redirect_uri"]:
            return JSONResponse(
                {
                    "error": "invalid_grant", 
                    "error_description": "redirect_uri mismatch"
                },
                status_code=400
            )
        
        """
        Issue JWT with session_id
        """
        session_id = code_data["session_id"]
        mcp_token = self.token_service.issue_token(
            session_id=session_id,
            scopes=code_data["scope"].split()
        )
        
        """
        Delete code (one-time use)
        """
        self._delete_authorization_code(code)
        
        logger.info(f"Issued token for session {session_id}")
        
        return JSONResponse({
            "access_token": mcp_token,
            "token_type": "Bearer",
            "expires_in": SESSION_VALIDITY_SECS,
            "scope": code_data["scope"]
        })

    """
    Returns 501 for client registration attempts
    """
    async def _registration_not_supported(
        self, request: Request
    ) -> JSONResponse:
        return JSONResponse(
            {
                "info": "registration_not_supported",
                "info_message": "This server does not require client registration."
            },
            status_code=501
        )

    """
    Validate redirect_uri format
    """
    def _is_valid_redirect_uri(
        self, 
        redirect_uri: str
    ) -> bool:
        try:
            parsed = urlparse(redirect_uri)
            """
            Allow localhost for development
            """
            if parsed.hostname in ["localhost", "127.0.0.1"]:
                return True
            """
            Allow HTTPS in production
            """
            if parsed.scheme == "https":
                return True
            return False
        except Exception as e:
            logger.error(f"Error in validating redirect url : {e}")
            return False
    
    """
    Store authorization code temporarily
    """
    def _store_authorization_code(
        self, auth_code: str, code_data: Dict
    ):
        key = f"{AUTH_CODE_KEY_PREFIX}{auth_code}"
        redis_client.json().set(key, "$", json.dumps(code_data))
        redis_client.expire(key, SESSION_VALIDITY_SECS)
        logger.info(f"Stored auth code: {auth_code}")
    
    """
    Retrieve authorization code
    """
    def _retrieve_authorization_code(
        self, auth_code: str
    ) -> Optional[Dict]:
        key = f"{AUTH_CODE_KEY_PREFIX}{auth_code}"
        data = redis_client.json().get(key)
        return json.loads(data) if data else None
    
    """
    Delete authorization code after exchange
    """
    def _delete_authorization_code(
        self, auth_code: str
    ):
        key = f"{AUTH_CODE_KEY_PREFIX}{auth_code}"
        redis_client.json().delete(key, "$")
    
    """
    Validate PKCE (S256 method)
    """
    def _validate_pkce(
        self, 
        code_verifier: str, 
        code_challenge: str
    ) -> bool:
        if not code_verifier or not code_challenge:
            return False
        
        computed_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        return computed_challenge == code_challenge