import jwt
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from conn.redis_config import redis_client
from config import (
    TOKEN_PARAMETER,
    SESSION_VALIDITY_SECS,
    ISSUER,
    AUDIENCE,
    ALGORITHM,
    TOKEN_KEY_PREFIX
)
from log.logger import logger
from session.manager import SessionManager

session_manager = SessionManager()

"""
Issues and validates MCP-specific bearer tokens
"""
class MCPTokenService:
    """
    constructor for the token issue and validate service
    """
    def __init__(self):
        self.issuer = ISSUER
        self.audience = AUDIENCE
        self.algorithm = ALGORITHM
        self.token_ttl = SESSION_VALIDITY_SECS
    
    """
    Issue JWT bearer token for MCP access
    Maps to session_id which contains credentials
        
    Token Payload:
        - session_id: Redis session key
        - aud: MCP server URI (audience binding)
        - iss: MCP server URI (issuer)
        - exp: Expiration time (Unix timestamp)
        - iat: Issued at time (Unix timestamp)
        - scope: Granted scopes
        - jti: Unique token ID (for revocation)
    """
    def issue_token(
        self,
        session_id: str,
        scopes: list = None
    ) -> str:
        now = datetime.now(timezone.utc)
        token_id = secrets.token_urlsafe(16)
        
        payload = {
            "session_id": session_id,
            "aud": self.audience,
            "iss": self.issuer,
            "exp": int((now + timedelta(seconds=self.token_ttl)).timestamp()),
            "iat": int(now.timestamp()),
            "scope": scopes or [], #scope of mcp
            "jti": token_id
        }
        
        token = jwt.encode(payload, TOKEN_PARAMETER, algorithm=self.algorithm)
        
        """
        Store token mapping in Redis
        """
        self._store_token(token_id, session_id)
        
        logger.info(f"Issued JWT token {token_id} for session {session_id}")
        
        return token
    
    """
    Validate MCP bearer token
    Returns decoded payload if valid, None otherwise
    """
    def validate_token(
        self, token: str
    ) -> Optional[Dict]:

        session_id = None
        try:
            payload = jwt.decode(
                token,
                TOKEN_PARAMETER,
                algorithms=[self.algorithm],
                audience=self.audience,
                issuer=self.issuer
            )

            session_id = payload['session_id']
            
            logger.info(f"Token decoded for session {session_id}")
            
            """
            Check if token is revoked
            """
            if self._is_token_revoked(payload["jti"]):
                logger.error(f"Token {payload['jti']} is revoked")
                return None
            
            """
            Verify session still exists
            """
            session_exists = session_manager.validate(session_id)
            if not session_exists:
                logger.error(f"Session not found in Redis: {session_id}")
                return None
            
            logger.info(f"Token validated for session {session_id}")
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.error(f"Error in validating token: Token expired for session id : {session_id}")
            return None
        except jwt.InvalidAudienceError:
            logger.error(f"Error in validating token: Invalid token audience (expected: {self.audience}) for session id : {session_id}")
            return None
        except jwt.InvalidTokenError as e:
            logger.error(f"Error in validating token: Invalid token: {e} for session id : {session_id}")
            return None
        except Exception as e:
            logger.error(f"Error in validating token: Unexpected error validating token: {e} for session id : {session_id}")
            return None
    
    """
    Store token metadata for revocation checks
    Uses simple Redis string (not RedisJSON for compatibility)
    """
    def _store_token(
        self, 
        token_id: str, 
        session_id: str
    ):
        key = f"{TOKEN_KEY_PREFIX}{token_id}"
        token_data = {
            "session_id": session_id,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "revoked": False
        }
        
        redis_client.json().set(
            key,
            "$",
            json.dumps(token_data)
        )
        redis_client.expire(key, SESSION_VALIDITY_SECS)
        logger.info(f"Stored token metadata: {token_id} for session id : {session_id}")

    """
    Check if token has been explicitly revoked
    """
    def _is_token_revoked( 
        self, 
        token_id: str
    ) -> bool:
        key = f"{TOKEN_KEY_PREFIX}{token_id}"
        
        token_data = redis_client.json().get(key)
        if not token_data:
            logger.error(f"Error in checking if token has been explicitly revoked: Token metadata not found: {token_id}")
            return True
        
        token_data = json.loads(token_data)
        return token_data.get("revoked", False)