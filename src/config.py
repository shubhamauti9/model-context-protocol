import datetime
import os
import logging
import argparse
from typing import Any, List
from dotenv import load_dotenv

logger = logging.getLogger("config")

def load_environment(env):
    """
    Load the environment variables based on the provided env
    """
    env_file = f"{env}.env"
    
    if os.path.exists(env_file):
        load_dotenv(dotenv_path=env_file)
        logger.info(f"Loaded {env_file} successfully.")
    else:
        logger.error(f"{env_file} not found.")
        raise FileNotFoundError(f"{env_file} not found.")

def parse_args():
    parser = argparse.ArgumentParser(description="Run with specified environment profile.", add_help=False)
    parser.add_argument(
        "--env",
        type=str,
        default="uat",
        help="Environment profile to use (e.g., uat or prod)"
    )
    """
    Parse known args to avoid breaking on unknown ones like --cov
    """
    args, _ = parser.parse_known_args()
    return args

args = parse_args()

load_environment(args.env)

"""
A configuration variable
"""
#app-version
APP_VERSION = os.getenv("APP_VERSION")

#api-version-id
VERSION_ID = os.getenv("VERSION_ID")

#app-port
HOST = os.getenv("MCP_HOST")

#app-host
PORT = os.getenv("MCP_PORT") or 6901

#redis-host
REDIS_HOST = os.getenv("REDIS_HOST") or "http://127.0.0.1"

#redis-port
REDIS_PORT = os.getenv("REDIS_PORT") or 6379

#redis-p
REDIS_P = os.getenv("REDIS_P") or ""

#redis-db
REDIS_DB = os.getenv("REDIS_DB") or 0

#app-log-file
LOG_PATH = os.getenv("LOG_FILE")

#encoding-type
ENCODING = os.getenv("ENCODING")

#api-base-url
BASE_URL = os.getenv("API_BASE_URL")

#api-key
API_KEY = os.getenv("API_KEY")

#session-validity
SESSION_VALIDITY = datetime.timedelta(hours=1)
SESSION_VALIDITY_SECS = 3600

#session-redis-key-prefix
SESSION_KEY_PREFIX = "session:"

#auth-code-redis-key-prefix
AUTH_CODE_KEY_PREFIX = "auth_code:"

#token-redis-key-prefix
TOKEN_KEY_PREFIX = "token:"

LOG_LEVEL = {
    'critical': "CRITICAL",
    'fatal': "FATAL",
    'error': "ERROR",
    'warn': "WARNING",
    'info': "INFO",
    'debug': "DEBUG"
}