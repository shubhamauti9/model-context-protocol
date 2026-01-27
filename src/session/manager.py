import datetime
from typing import Any, Optional , List
import uuid
from exception.error import Error
from log.logger import logger, session_logger
from session.session import Session
from conn.redis_config import redis_client
from config import (
    SESSION_KEY_PREFIX,
    SESSION_VALIDITY,
    SESSION_VALIDITY_SECS
)

"""
A class to manage sessions for the application.
Encapsulates the logic for session management, including:
- Session creation and storage
- Session validation and expiry handling
- Session data retrieval and updates
- Session cleanup and expiration
"""
class SessionManager:
    """
    Implements the Singleton design pattern for the SessionManager class.
    """
    _instance = None

    """
    Implements the Singleton design pattern for the SessionManager class.
    Initializes the SessionManager with necessary dependencies.
    This method will only execute its core initialization logic once,
    even if the SessionManager class is "instantiated" multiple times
    due to the Singleton pattern.
    Returns:
        SessionManager: The singleton instance of the SessionManager class.
    """
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SessionManager, cls).__new__(cls)
            logger.info("SessionManager instance created.")
        return cls._instance

    def __init__(self) -> None:
        pass

    """
    Helper to construct the Redis key for a session.
    """
    def _get_redis_key(self, session_id: str, prefixKey : Optional[str] = None) -> str:
        if not prefixKey : 
           return f"{SESSION_KEY_PREFIX}{session_id}"
        return f"{prefixKey}{session_id}"
    
    """
    Helper to update any key of a session in redis
    """
    def _update_key(self, session_id: str, key: str, value: Any):
        redis_key = self._get_redis_key(session_id=session_id)
        exists = redis_client.exists(redis_key)
        if exists:
            redis_client.json().set(redis_key, f"$.{key}", value)

    """
    Helper to fetch value of a particular key from redis of a session
    """
    def _fetch_value(self, session_id: str, key: str) -> Optional[Any]:
        redis_key = self._get_redis_key(session_id=session_id)
        exists = redis_client.exists(redis_key)
        if exists:
            result: Optional[list[Any]] = redis_client.json().get(redis_key, f"$.{key}")
            if result is not None and len(result) > 0:
                if isinstance(result[0], (dict, list)):
                    return result[0]
                else:
                    return str(result[0])
            else:
                return None
        return None
    
    """
    Creates a new session and saves it to Redis.
    Always updates the 'last_active' timestamp.
    This is called by tools to manage session lifecycle.
    This session_id is typically the FastMCP mcp_session_id.

    Returns:
        str: The session ID.
        This session_id is typically the FastMCP mcp_session_id.
    """
    def generate(self) -> str:
        session_id = uuid.uuid4().hex
        redis_key = self._get_redis_key(session_id)
        exists = redis_client.exists(redis_key)
        if not exists:
            session = Session(session_id)
            session_logger(session_id, "info", "Session Created")            
            redis_client.json().set(redis_key, "$", session.to_dict())
            redis_client.expire(redis_key , SESSION_VALIDITY_SECS)
            session_logger(session_id, "info", "Session saved in Redis")  

        redis_client.json().set(redis_key, "$.last_active", datetime.datetime.now().isoformat())
        return session_id
    
    """
    Ensures a session exists for the given ID. If it doesn't, creates it.
    Always updates the 'last_active' timestamp.
    This is called by tools to manage session lifecycle.
    This session_id is typically the FastMCP mcp_session_id.
    """
    def generateById(self, session_id: str):
        redis_key = self._get_redis_key(session_id)
        exists = redis_client.exists(redis_key)
        if not exists:
            session = Session(session_id)
            session_logger(session_id, "info", "Session Created")
            redis_client.json().set(redis_key, "$", session.to_dict())
            redis_client.expire(redis_key , SESSION_VALIDITY_SECS)
            session_logger(session_id, "info", "Session saved in Redis")  

        redis_client.json().set(redis_key, "$.last_active", datetime.datetime.now().isoformat())
        return session_id
        
    """
    Retrieves data for a given session ID.
    Also updates the 'last_active' timestamp if session exists.
    """
    def retrieve(self, session_id: str) -> Optional[Session]:
        if not session_id:
            logger.error(Error.__str__(Error("Session Id should not be blank", 400)))
            return None
        redis_key = self._get_redis_key(session_id)
        exists = redis_client.exists(redis_key)
        if not exists:
            session_logger(session_id, "error", "Session ID does not exist")
            return None
        retrieved_data = redis_client.json().get(redis_key)

        if retrieved_data is None:
            session_logger(session_id, "error", "Failed to retrieve data for session ID, Data was none")
            return None

        if not isinstance(retrieved_data, dict):
            session_logger(session_id, "error", "Data retrieved for session ID is not a dictionary")
            return None
        
        try:
            session = Session.from_dict(retrieved_data) 
            session.update_activity()
            updated_session_dict = session.to_dict()
            redis_client.json().set(redis_key, '.', updated_session_dict)
            session_logger(session_id, "info", "Updated 'last_active' for session and saved back to Redis")
            return session
        except KeyError as e:
            session_logger(session_id, "error", "Missing key in retrieved session data")
            return {"error": str(e)}
        except Exception as e:
            session_logger(session_id, "error", "Error converting retrieved data to Session object")
            return {"error": str(e)}
    
    """
    Validates whether session is still active or expired
    """
    def validate(self, session_id: str) -> bool:
        redis_key = self._get_redis_key(session_id=session_id)
        exists = redis_client.exists(redis_key)
        if exists:
            return True
        else:
            session_logger(session_id, "error", "session does not exist with session id")
            return False
        
    
    """
    Extends the expiry of a specific session.
    """
    def extendSessionExpiry(self, session_id: str) -> bool:
        redis_key = self._get_redis_key(session_id=session_id)
        exists = redis_client.exists(redis_key)
        if exists:
            updatedExpiry = (datetime.datetime.now() + SESSION_VALIDITY)
            redis_client.expire(redis_key , SESSION_VALIDITY_SECS)
            self._update_key(session_id, "expiry", str(updatedExpiry))
            session_logger(session_id, "info", "Session expiry extended")
            return True
        else:
            session_logger(session_id, "error", "Cannot extend expiry for non-existent session")
            return False
        
    """
    cleanup session 
    """
    def cleanupSession(self, session_id:str) -> Any:
        redis_key = self._get_redis_key(session_id=session_id)
        exists = redis_client.exists(redis_key)
        if exists:
            redis_client.json().delete(redis_key)
        else:
            session_logger(session_id, "error", "Cannot delete for non-existent session")
            return {}