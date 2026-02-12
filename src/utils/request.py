from typing import Any
import requests
from requests import Response
import json

from config import (
    BASE_URL
)

from urllib.parse import urljoin
from exception.error import Error
from log.logger import logger, session_logger

"""
A class for making HTTP requests to the API
"""
class CustomRequest:
    """
    The root URL for the API
    """
    _rootUrl = str(BASE_URL)

    """ 
    The accept header for the API
    """
    accept = "application/json"

    """
    The routes for the API
    """
    _routes = {
        "api.tool1": f"Enter your API route here (can add parameters here)"
    }

    """
    Initialize the CustomRequest class with the given parameters
    Args:
        api_key (str): The API key to use for the request
        access_token (str): The access token to use for the request
        state (str): The state could be used to verify MCP session for the request
        debug (bool): Whether to enable debug mode (default: False)
    """
    def __init__(
        self, api_key=None, access_token=None, state=None, debug=False
    ):
        self.api_key = api_key
        self.access_token = access_token
        self.state = state
        self.debug = debug
    """
    Build a URL for the given API route and parameters.
    Args:
        api (str): The API route key.
        params (dict): Parameters to format into the route.
    Returns:
        str: The full URL.
    """
    def urlBuilder(
        self, api: str, params: dict[Any, Any]
    ) -> str:
        if api not in self._routes:
            raise Error(f"API route '{api}' not found in routes", 404)
        route_template = self._routes[api]
        try:
            route = route_template.format(**params)
        except KeyError as e:
            raise Error(f"Missing parameter for route '{api}': {e}", 400)
        url = urljoin(self._rootUrl, route)
        return url

    """
    Alias for creating request headers
    Args:
        None
    Returns:
        dict[str, str]: The request headers
    """
    def requestHeaders(self) -> dict[str, str]:
        headers = {
            "Content-type": self.accept
        }
        if self.api_key:
            headers["api-key"] = self.api_key
        if self.access_token:
            headers["access-token"] = self.access_token
        if self.state:
            headers["state"] = self.state
        return headers

    """
    Alias for creating response
    Args:
        content (dict): The content of the response
        code (int): The status code of the response
    Returns:
        Response: The response object
    """
    def _response(
        self, content: dict, code: int
    ) -> Response:
        response = Response()
        response.status_code = code
        response._content = json.dumps(content).encode("utf-8")
        response.headers['Content-Type'] = self.accept
        return response

    """
    Alias for sending a DELETE request
    Args:
        route (str): The route to send the request to
        params (dict): The parameters to send with the request
    Returns:
        Response: The response object
    """
    def _deleteRequest(self, route, params=None):
        return self._request(route, "DELETE", params)

    """
    Alias for sending a PUT request
    Args:
        route (str): The route to send the request to
        params (dict): The parameters to send with the request
    Returns:
        Response: The response object
    """
    def _putRequest(self, route, params=None):
        return self._request(route, "PUT", params)

    """
    Alias for sending a POST request
    Args:
        route (str): The route to send the request to
        params (dict): The parameters to send with the request
    Returns:
        Response: The response object
    """
    def _postRequest(self, route, params=None):
        return self._request(route, "POST", params)

    """
    Alias for sending a GET request
    Args:
        route (str): The route to send the request to
        params (dict): The parameters to send with the request
    Returns:
        Response: The response object
    """
    def _getRequest(self, route, params=None):
        return self._request(route, "GET", params)
    
    """
    Make an HTTP request
    Args:
        route (str): The route to send the request to
        method (str): The method to use for the request
        parameters (dict): The parameters to send with the request
        data (dict): The data to send with the request
    Returns:
        Response: The response object
    """
    def _request(
        self, route, method, parameters=None, data=None, baseUrl=None
    ) -> Response:
        """
        Send a request to the given URL with the given 
            method
            data
            params
            headers
            allow_redirects
        """
        params = parameters.copy() if parameters else {}
        """
        Format the route with the given parameters
        """
        uri = self._routes[route].format(**params)  
        if baseUrl is None:
            baseUrl = self._rootUrl
        """
        Join the root URL with the formatted route
        """
        url = urljoin(baseUrl, uri)
        """
        Create the request headers
        """
        headers = self.requestHeaders()
        """
        Log the request details if debug mode is enabled
        """
        if self.debug:
            session_logger(
                self.state,
                "info",
                f"Request: method- {method} url- {url} params- {params} headers- {headers} data- {data}",
                "CustomRequest"
            )
        """
        Initialize the response text
        """
        rtext = None
        try:
            """
            Send a request to the given URL with the given method, data, params, headers and allow_redirects
            Args:
                method (str): The method to use for the request
                url (str): The URL to send the request to
                data (dict): The data to send with the request
                params (dict): The parameters to send with the request
                headers (dict): The headers to send with the request
                allow_redirects (bool): Whether to allow redirects (default: True)
            """
            r = requests.request(
                    method,
                    url,
                    data=json.dumps(data) if method in ["POST", "PUT"] else None,
                    params=json.dumps(params) if method in ["POST", "PUT", "GET", "DELETE"] else None,
                    headers=headers,
                    allow_redirects=True
                )
            rtext = r.text
        except requests.exceptions.RequestException as e:
            """
            Handle network or API errors
            """
            error = {
                "error": f"Network or API error: {e}",
                "status_code": 500,
                "raw_response": rtext
            } 
            logger.error(Error.__str__(Error(f"Network or API error: {e}", 500)))
            return self._response(content=error, code=500)
        except Exception as e:
            """
            Handle unexpected errors
            """
            error = {
                "error": f"Unexpected error: {e}",
                "raw_response": rtext
            }
            logger.error(Error.__str__(Error(f"Unexpected error: {e}", 500)))
            return self._response(content=error, code=500)

        """
        Log the response if debug mode is enabled
        """
        if self.debug:
            logger.debug(
                "Response: {code} {content}".format(
                    code=r.status_code,
                    content=r.content
                )
            )   
            
        # Handle 204 No Content or empty body BEFORE JSON parsing
        if r.status_code == 204 or not (rtext and rtext.strip()):
            error = {
                "error": "No data found in response",
                "full_response": None
            }
            logger.error(Error.__str__(Error("No data found in response", 204)))
            return self._response(content=error, code=204)


        try:
            """
            Decode the response as JSON
            """
            data = r.json()
        except ValueError:
            """
            Handle JSON decoding errors
            """
            error = {
                "error": "Failed to decode JSON response",
                "raw_response": r.text
            }
            logger.error(Error.__str__(Error("Failed to decode JSON response", 400)))
            return self._response(content=error, code=400)
        
        # JSON parsed but is empty (None, {}, or [])
        if data is None or (isinstance(data, (dict, list)) and not data):
            error = {
                "error": "No data found in response",
                "full_response": data
            }
            logger.error(Error.__str__(Error("No data found in response", 204)))
            return self._response(content=error, code=204)

        """
        Return the response
        """
        return self._response(content=data, code=r.status_code)