import datetime
from typing import Any, Dict, List

from config import SESSION_VALIDITY
from log.logger import session_logger

"""
A class to represent an individual client session.
"""
class Session:
    """
    Represents an individual client session.
    this session object might contain any other required fields for mcp use case
    also addition of getter and setter for this extra fields
    """
    def __init__(
            self,
            session_id: str,
            data: Dict[str, Any] | None = None,
            connected_at: str | None = None,
            last_active: str | None = None,
            expiry: str | None = None
        ) -> None:
        self.id: str = session_id
        self.connected_at: str = connected_at if connected_at is not None else datetime.datetime.now().isoformat()
        self.last_active: str = last_active if last_active is not None else datetime.datetime.now().isoformat()
        self.expiry: str = expiry if expiry is not None else (datetime.datetime.now() + SESSION_VALIDITY).isoformat()
        self.data: Dict[str, Any] = data or {}

    """
    Updates the last_active timestamp for this session
    """
    def update_activity(self):
        self.last_active = datetime.datetime.now().isoformat()

    """
    Gets the data for this session
    """
    def get_data(self) -> Dict:
        return self.data

    """
    Gets the data by key for this session
    """
    def getDataById_data_key(self, key: str) -> Any:
        return self.data[key]

    """
    Adds the data for this session
    """
    def add_data(self, key: str, value: Any):
        self.data[key] = value
        self.update_activity()

    """
    Returns whether the session is expired or not
    """
    def isExpired(self) -> bool:
        try:
            """
            Convert the ISO format expiry string back to a datetime object for comparison
            """
            return datetime.datetime.now() > datetime.datetime.fromisoformat(self.expiry)
        except (TypeError, ValueError):
            session_logger(self.id, "error", "Invalid expiry format for session")
            return True

    """
    Converts the Session object to a dictionary for JSON serialization
    """
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "connected_at": self.connected_at,
            "last_active": self.last_active,
            "expiry": self.expiry,
            "data": self.data
        }

    """
    Creates a Session object from a dictionary (JSON deserialization)
    Use .get() with default values to handle cases where fields might be missing
    In older stored data or if the schema changes
    """
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            session_id=data["id"],
            connected_at=data.get("connected_at"),
            last_active=data.get("last_active"),
            expiry=data.get("expiry"),
            data=data.get("data", {})
        )