from redis import Redis
from config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_P,
    REDIS_DB
)
from log.logger import logger
from encryptdecrypt.encryptdecrypt import decrypt

"""
A Redis client instance for the application.
"""
try:
    redis_client = Redis(REDIS_HOST, int(REDIS_PORT), int(REDIS_DB), decrypt(REDIS_P).decode())
except Exception as e:
    logger.error(f"Error while creating redis connection with {REDIS_HOST} and error {e} ")
    raise e
logger.info(f"Redis client initialized successfully with host: {REDIS_HOST} and port: {REDIS_PORT}")