import logging
import structlog
import datetime
from config import (
    LOG_LEVEL,
    LOG_PATH
)

"""
Set up the standard logging to write to a file
"""
logging.basicConfig(
    filename=LOG_PATH,
    filemode='a',
    format='%(message)s',
    level=logging.INFO
)

"""
Define a custom processor that formats the log record as a string
"""
def formatter(logger, method_name, event_dict):
    timestamp = event_dict.pop("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())
    
    """
    Get and capitalize level, then pad it to a fixed width (e.g., 8 characters)
    Common levels are INFO, WARN, ERROR, DEBUG, CRITICAL. Max length is CRITICAL (8 chars)
    """
    level = event_dict.pop("level", "info").upper().ljust(8)
    log_name = event_dict.pop("logger", "unknown")
    event = event_dict.pop("event", "")

    """
    Join any remaining extra fields as key=value pairs, if they exist
    """
    extra_fields = " ".join([f"{k}={v}" for k, v in event_dict.items() if v is not None])

    """
    Construct the desired format
    """
    if extra_fields:
        message = f"{event} {extra_fields}"
    else:
        message = event

    """
    Return the fully formatted string: timestamp[level]logName -- message
    """
    return f"{timestamp} [{level}] {log_name} -- {message}"

"""
Configure structlog to use standard logging
"""
structlog.configure(
    processors=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        formatter
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

"""
Object that returns logger for every class
"""
logger = structlog.get_logger("MASK-MCP")

"""
custom session logger
"""
def session_logger(
    session_id : str,
    level : str | None = None,
    message : str | None = None,
    method : str | None = None,
    userid : str | None = None
):
    if level is None:
        level = "info"
    ln = LOG_LEVEL.get(level.lower())
    m = None
    if method is not None:
        if userid is not None:
            m = f"{method} - {userid} - {message}"
        else:
            m = f"{method} - {message}"
    else:
        if userid is not None:
            m = f"{userid} - {message}"
        else:
            m = message
    match ln:
        case "ERROR":
            logger.error(f"{session_id} - {m}")
        case "INFO":
            logger.info(f"{session_id} - {m}")
        case "DEBUG":
            logger.debug(f"{session_id} - {m}") 
        case "WARNING":
            logger.warn(f"{session_id} - {m}")
        case "FATAL":
            logger.fatal(f"{session_id} - {m}")
        case "CRITICAL":
            logger.critical(f"{session_id} - {m}")