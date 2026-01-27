from log.logger import logger

"""
A custom exception for demonstrating runtime error handling.
Inherits from RuntimeError to signify an error during program execution.
"""
class Error(RuntimeError):
    """
    A custom exception for demonstrating runtime error handling.
    Inherits from RuntimeError to signify an error during program execution.
    """
    def __init__(
        self, message : str, code : int
    ):
        """
        Call the base class constructor with the message
        """
        super().__init__(message)
        """
        Store additional custom information
        """
        self.code = code
        self.message = message
        logger.error(f"Runtime Exception raised : {message} (Code: {code})")

    def __str__(self):
        """
        Custom string representation for the exception.
        """
        if self.code:
            return f"Runtime Exception raised : {self.message} (Code: {self.code})"
        return self.message

    @staticmethod
    def throw(cls, message: str, code: int):
        """
        A static method to raise an instance of this custom error.
        """
        raise cls(message, code)