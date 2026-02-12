"""
Define utility methods
"""

from typing import Any
from log.logger import logger
class Helpers:
    """
    Helpers class for the application
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Helpers, cls).__new__(cls)
            logger.info("helpers instance created.")
        return cls._instance

    """
    Initialize the Helpers class
    """
    def __init__(self):
        pass
    

    """
        Mask the value of the given string      
        Args:
            s (Any): The value to mask
            unmasked_left (int): The number of characters to leave unmasked on the left
            unmasked_right (int): The number of characters to leave unmasked on the right
            mask_char (str): The character to use for masking
        Returns:
            Any: The masked value
        """
    @staticmethod
    def mask_value(
        s: Any,
        unmasked_left: int = 0,
        unmasked_right: int = 0,
        mask_char: str = '*'
    ) -> Any:
        if not isinstance(s, (str, int, float)):
            return s

        s_str = str(s)
        total_length = len(s_str)

        """
        Ensure unmasked counts are non-negative integers
        """
        unmasked_left = max(0, int(unmasked_left))
        unmasked_right = max(0, int(unmasked_right))

        """
        If unmasked characters exceed total length, fallback to (1, 0)
        """
        if unmasked_left + unmasked_right >= total_length:
            unmasked_left = 1
            unmasked_right = 0

        """
        Build masked string
        """
        left_part = s_str[:unmasked_left]
        right_part = s_str[-unmasked_right:] if unmasked_right > 0 else ''
        masked_middle = mask_char * (total_length - unmasked_left - unmasked_right)

        return left_part + masked_middle + right_part