import urllib
import uuid
import anyio
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from session.manager import SessionManager
from utils.helpers import Helpers
from log.logger import (
    logger,
    session_logger
)
from config import (
    APP_VERSION,
    RESOURCE,
    AUTH_SERVER_URI,
    BEARER_REALM
)

from anyio.abc import TaskStatus

from starlette.responses import JSONResponse
from starlette.requests import Request
from pydantic import ValidationError
from sse_starlette import EventSourceResponse
from starlette.responses import Response
from starlette.types import Receive, Scope, Send
from starlette.responses import Response

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.streamable_http import(
    MCP_SESSION_ID_HEADER,
    StreamableHTTPServerTransport
)
import mcp.types as types
from mcp.shared.message import ServerMessageMetadata, SessionMessage

from auth.token import MCPTokenService

helpersInstance = Helpers()
customSessionManager = SessionManager()

"""
provides a low level server from FastMcp server
"""
class CustomMiddleware:
    """
    provides a low level server from FastMcp server
    """
    def __init__(self, mcp: FastMCP):
        self.mcp_server = mcp._mcp_server
        """
        Create the session manager with true stateful mode
        """
        self.session_manager = StreamableHTTPSessionManager(
            app=self.mcp_server,
            event_store=None,
            json_response=True
        )
        """
        Initialize MCP token service for OAuth
        """
        self.mcp_token_service = MCPTokenService()
        logger.info("CustomMiddleware initialized with OAuth support")
        """
        defines a sse message communication endpoint
        """
        self.sse_endpoint = "/messages/"
        """
        defines a empty dict for stream writers
        to mock this as stateful using session id
        """
        self.sse_streams: dict[Any, Any] = {}

    """
    SSE connection handler for stateless HTTP communications
    """
    @asynccontextmanager
    async def connect_sse(
        self, scope: Scope, receive: Receive, send: Send
    )->None:

        """
        Checking Whether Connection is HTTP
        """
        if scope["type"] != "http":
            logger.error("connect_sse received non-HTTP request")
            raise ValueError("connect_sse can only handle HTTP requests")
        
        """
        Create memory streams for bidirectional communication
        """
        """
        Client to Server
        Purpose: This channel carries messages from the client to the application

        read_stream_writer: This is the entry in slot (pipeline)
            When a message arrives from a client via an HTTP POST request,
            the request handler will use this to send the message into the channel
            Type: MemoryObjectSendStream[SessionMessage | Exception]

        read_stream: This is the exit out slot 
            The main application will wait here to receive and process new messages as they arrive
            Type: MemoryObjectReceiveStream[SessionMessage | Exception]

        --- The type hint indicates that channel can carry either a valid message or an Exception object, 
            which is useful for telling the application that a message failed to parse
        """
        read_stream_writer, read_stream = anyio.create_memory_object_stream(0)

        """
        Server to Client
        Purpose: This channel carries messages from the application to the client

        write_stream: This is the entry in slot (pipeline) 
            When the main application wants to send a reply, it will put the message in here
            Type: MemoryObjectSendStream[SessionMessage | Exception]

        write_stream_reader: This is the exit out slot
            A separate background task (the SSE handler) will wait here to receive messages
            forward them to the client over the network
            Type: MemoryObjectReceiveStream[SessionMessage | Exception]

        --- The type hint indicates that channel can carry either a valid message or an Exception object, 
            which is useful for telling the application that a message failed to parse
        """
        write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

        """
        Generate unique session ID for this SSE connection
        """
        session_id = uuid.uuid4().hex
        self.sse_streams[session_id] = read_stream_writer
        session_logger(
            session_id,
            "info",
            "Created new SSE session with ID"
        )

        """
        creates and stores session in redis
        """
        customSessionManager.generateById(session_id)

        """
        Determine the full path for the message endpoint
        """
        sse_messages_endpoint = f"{self.sse_endpoint}?session_id={session_id}"

        """
        Create SSE stream writer and reader for sending events to client
        """
        sse_stream_writer, sse_stream_reader = anyio.create_memory_object_stream[dict[str, Any]](0)

        """
        Write messages to SSE stream
        """
        async def sse_writer():
            session_logger(
                session_id,
                "info",
                f"Starting SSE writer for this session : {session_id}"
            )

            """
            Send endpoint information to client
            """
            async with sse_stream_writer, write_stream_reader:
                await sse_stream_writer.send({
                    "event": "endpoint", 
                    "data": sse_messages_endpoint
                })
                session_logger(
                    session_id,
                    "info",
                    f"Sent endpoint event: {sse_messages_endpoint}"
                )

                """
                Forward messages from MCP server to SSE client
                """
                async for session_message in write_stream_reader:
                    await sse_stream_writer.send({
                        "event": "message",
                        "data": session_message.message.model_dump_json(by_alias=True, exclude_none=True),
                    })
                    session_logger(
                        session_id,
                        "info",
                        f"Sending message via SSE: {session_message}"
                    )

        """
        Handle SSE response and cleanup on disconnect
        """
        async with anyio.create_task_group() as task_group:
            async def response_wrapper(
                scope: Scope, receive: Receive, send: Send
            ):
                try:
                    session_logger(
                        session_id,
                        "info",
                        "Entering EventSource Wrapper"
                    )
                    await EventSourceResponse(
                        content=sse_stream_reader, 
                        data_sender_callable=sse_writer
                    )(scope, receive, send)
                except Exception as e:
                    session_logger(
                        session_id,
                        "error",
                        f"Error in EventSource Wrapper : {e}"
                    )
                finally:
                    """
                    Cleanup streams when client disconnects
                    """
                    await read_stream_writer.aclose()
                    await write_stream_reader.aclose()

                    """
                    Remove session from active sessions
                    """
                    self.sse_streams.pop(session_id, None)
                    session_logger(
                        session_id,
                        "info",
                        f"SSE client session disconnected: {session_id}"
                    )

            session_logger(
                session_id,
                "info",
                "Starting SSE response task"
            )
            task_group.start_soon(
                response_wrapper,
                scope,
                receive,
                send
            )
            
            """
            hands over the read_stream and write_stream to the application
            out of context manager defination
            """
            session_logger(
                session_id,
                "info",
                "Yielding read and write streams for application"
            )
            yield (read_stream, write_stream)
    
    """
    Custom ASGI middleware for SSE endpoint
    """
    async def handle_sse(
        self, request: Request
    ) -> Response:
        try:
            async with self.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                read_stream, write_stream = streams
                """
                Run server with stateless mode
                """
                await self.mcp_server.run(
                    read_stream,
                    write_stream,
                    self.mcp_server.create_initialization_options(),
                    stateless=True
                )
            """
            Return empty response to avoid NoneType error
            """
            return Response()
        except Exception as e:
            logger.error(f"Error in SSE handler: {e}")
            return Response("Internal Server Error", status_code=500)

    """
    Handle POST messages for SSE sessions
    """
    async def handle_sse_message(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        request = Request(scope, receive)

        """
        Get session ID from query parameters
        """
        session_id = request.query_params.get("session_id")
        if session_id is None:
            logger.error(
                "Received SSE POST request without session_id"
            )
            response = Response("session_id is required", status_code=400)
            return await response(scope, receive, send)

        try:
            headers = list(scope['headers'])
            headers.append(
                (MCP_SESSION_ID_HEADER.encode(), session_id.encode())
            )
            scope["headers"] = headers
        except ValueError:
            logger.error(
                f"Received invalid SSE session ID: {session_id}"
            )
            response = Response("Invalid session ID", status_code=400)
            return await response(scope, receive, send)

        """
        Find the writer for this session
        """
        writer = self.sse_streams.get(session_id)
        if not writer:
            logger.error(
                f"Could not find SSE session for ID: {session_id}"
            )
            response = Response("Could not find session", status_code=404)
            return await response(scope, receive, send)

        """
        Parse the JSON message
        """
        body = await request.body()
        session_logger(
            session_id,
            "info",
            f"Received SSE JSON: {body}"
        )

        try:
            message = types.JSONRPCMessage.model_validate_json(body)
            session_logger(
                session_id,
                "info",
                f"Validated SSE client message: {message}"
            )
        except ValidationError as err:
            logger.error(
                f"Failed to parse SSE message: {err}"
            )
            response = Response("Could not parse message", status_code=400)
            await response(scope, receive, send)
            await writer.send(err)
            return

        """
        Create session message with metadata
        """
        metadata = ServerMessageMetadata(request_context=request)
        session_message = SessionMessage(message, metadata=metadata)

        session_logger(
            session_id,
            "info",
            f"Sending SSE session message to writer: {session_message}"
        )
                
        """
        Send response and forward message to MCP server
        """
        response = Response("Accepted", status_code=202)
        await response(scope, receive, send)
        await writer.send(session_message)

    """
    Custom ASGI Middleware app for Streamable HTTP
    """
    async def handle_streamable_http(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        request = Request(scope, receive)
        session_id = request.headers.get(MCP_SESSION_ID_HEADER)
        if session_id is None:
            session_id = uuid.uuid4().hex
            headers = list(scope['headers'])
            headers.append(
                (MCP_SESSION_ID_HEADER.encode(), session_id.encode())
            )
            scope["headers"] = headers

            http_transport = StreamableHTTPServerTransport(
                mcp_session_id=session_id,
                is_json_response_enabled=True,
                event_store=None
            )

            self.session_manager._server_instances[session_id] = http_transport

            """
            Define the server runner
            """
            async def run_server(*, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
                async with http_transport.connect() as streams:
                    read_stream, write_stream = streams
                    task_status.started()
                    await self.session_manager.app.run(
                        read_stream,
                        write_stream,
                        self.session_manager.app.create_initialization_options(),
                        stateless=False
                    )

            assert self.session_manager._task_group is not None
            await self.session_manager._task_group.start(run_server)

            customSessionManager.generateById(session_id=session_id)
        else:
            current_session = customSessionManager.retrieve(session_id=session_id)

            if current_session is not None:
                current_session.update_activity()

        await self.session_manager.handle_request(scope, receive, send)

    """
    Handle OAuth Bearer token authentication.
    Extract and validate MCP token directly from request headers.
    OAuth Bearer token authentication (STATELESS)
    Used by: MCP Connectors, Claude Mobile
    Endpoint: /http
    """
    async def handle_http_request(
        self, request: Request
    ) -> Response:
        """
        OAuth Bearer token authentication for MCP
        """
        try:
            logger.info(f"{request.method} {request.url.path}")
            """
            Extract authorization header
            """
            auth_header = request.headers.get("authorization")

            """
            Check for Bearer token
            """
            if not auth_header or not auth_header.startswith("Bearer "):
                logger.error("Missing or invalid Authorization header")
                return JSONResponse(
                    {
                        "error": "unauthorized", 
                        "message": "Valid Bearer token required"
                    },
                    status_code=401,
                    headers={
                        "WWW-Authenticate": (
                            f'Bearer realm="{BEARER_REALM}", '
                            f'resource="{RESOURCE}", '
                            f'as_uri="{AUTH_SERVER_URI}"'
                        )
                    }
                )

            """
            Extract and validate token
            """
            mcp_token = auth_header[7:]
            token_payload = self.mcp_token_service.validate_token(mcp_token)

            if not token_payload:
                logger.error("Invalid or expired OAuth token")
                return JSONResponse(
                    {
                        "error": "unauthorized", 
                        "error_message": "Invalid or expired token"
                    },
                    status_code=401,
                    headers={
                        "WWW-Authenticate": (
                            f'Bearer realm="{BEARER_REALM}", '
                            f'resource="{RESOURCE}", '
                            f'as_uri="{AUTH_SERVER_URI}"'
                        )
                    }
                )

            """
            Extract session_id from token
            """
            session_id = token_payload["session_id"]
            logger.info(f"OAuth authenticated - session: {session_id}")

            """
            Verify session exists
            """
            session_exists = customSessionManager.retrieve(session_id=session_id)
            if not session_exists:
                logger.error(f"Session {session_id} not found in Redis")
                return JSONResponse(
                    {
                        "error": "session_not_found", 
                        "error_message": "Session not found"
                    },
                    status_code=401
                )

            """
            Inject session_id into scope
            """
            headers = list(request.scope['headers'])
            headers.append(
                (MCP_SESSION_ID_HEADER.encode(), session_id.encode())
            )
            headers.append(
                ("token_scopes".encode(), token_payload.get("scope", []))
            )
            request.scope["headers"] = headers

            """
            Setup transport if needed
            """
            if session_id not in self.session_manager._server_instances:
                logger.info(f"Creating transport for session {session_id}")
                
                http_transport = StreamableHTTPServerTransport(
                    mcp_session_id=session_id,
                    is_json_response_enabled=True,
                    event_store=None
                )

                self.session_manager._server_instances[session_id] = http_transport

                async def run_server(*, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
                    async with http_transport.connect() as streams:
                        read_stream, write_stream = streams
                        task_status.started()
                        await self.session_manager.app.run(
                            read_stream,
                            write_stream,
                            self.session_manager.app.create_initialization_options(),
                            stateless=False
                        )

                assert self.session_manager._task_group is not None
                await self.session_manager._task_group.start(run_server)

            """
            Update session activity
            """
            session = customSessionManager.retrieve(session_id=session_id)
            if session:
                session.update_activity()

            """
            Delegate to MCP ASGI handler and capture response
            """
            response_body = []
            response_status = 200
            response_headers = []

            async def send_capture(message):
                if message["type"] == "http.response.start":
                    nonlocal response_status, response_headers
                    response_status = message["status"]
                    response_headers = message.get("headers", [])
                elif message["type"] == "http.response.body":
                    response_body.append(message.get("body", b""))

            """
            Call ASGI handler
            """
            await self.session_manager.handle_request(request.scope, request.receive, send_capture)

            """
            Safe header decoding with error handling
            """
            headers_dict = {}
            for k, v in response_headers:
                try:
                    key = k.decode() if isinstance(k, bytes) else str(k)
                    value = v.decode() if isinstance(v, bytes) else str(v)
                    headers_dict[key] = value
                except Exception as e:
                    logger.error(f"Error in handle_http_request: Failed to decode header: {e} for session id : {session_id}")
            
            logger.info(f"Returning response: {response_status}")
            
            return Response(
                content=b"".join(response_body),
                status_code=response_status,
                headers=headers_dict
            )
            
        except Exception as e:
            logger.error(f"Error in handle_http_request: Unexpected error: {e} for session id : {session_id}", exc_info=True)
            return JSONResponse(
                {
                    "error": "internal_server_error", 
                    "error_message": f"Unexpected error: {e}"
                },
                status_code=500
            )
    
    """
    Define the new /redirect GET endpoint on the main Starlette app
    Callback endpoint to handle the redirect from the external login page
    It extracts the 'request_token' and 'state' (mcp_session_id) to generate the final access token
    after successful login and getting the access token, 
    mcp should inform llm that login successful and then llm should answer users query that they has asked before login if any
    """
    async def handle_redirect(
        self, request: Request
    ) -> Any:
        """
        Handles the OAuth callback redirect from the external login provider.

        This endpoint serves as the destination for the external login page's redirect.
        It is responsible for completing the authentication handshake by extracting
        temporary credentials and exchanging them for a persistent access token.

        **Workflow:**
        1.  **Extraction:** Manually parses the raw URL string to extract the information
            (to handle specific encoding edge cases) and retrieves the required parameter
            (which maps to the `mcp_session_id`).
        2.  **Validation:** Verifies that the session ID is present.
        3.  **Exchange:** processes the information retrieved for a valid user Access Token.
        4.  **Completion:** Logs the success/failure to the session logger and returns
            a JSON response instructing the browser/UI to close.

        Args:
            request (Request): The incoming HTTP request containing the full callback URL
                               with required parameters.

        Returns:
            JSONResponse:
                - **200 OK:** Login successful. Message instructs user to return to chat.
                - **400 Bad Request:** Missing parameters or invalid credentials.

        Dependencies:
            - `session_logger`: Used to log the flow state for specific user sessions.
        """
        method_name = "handle_redirect"
        logger.info(f"Callback endpoint hit with URL: {request.url}")
        # ... rest of your code

    async def health_check(
        self, request: Request
    ) -> Any:
        content = {
            "service" : "Model Context Protocol",
            "version" : APP_VERSION,
            "status" : "Service is Up and Running"
        }
        logger.info("HEALTHCHECK_API - Sharekhan Model Context Protocol's Liveliness Check Endpoint")
        return JSONResponse(content, 200)

    """
    RFC9728: Return 401 with WWW-Authenticate header
    Points to MCP server as both AS and RS
    """
    async def _send_401_unauthorized(
        self, scope: Scope, receive: Receive, send: Send
    ):
        response = JSONResponse(
            {"error": "unauthorized", "message": "Valid Bearer token required"},
            status_code=401,
            headers={
                "WWW-Authenticate": (
                    f'Bearer realm="{BEARER_REALM}", '
                    f'resource="{RESOURCE}", '
                    f'as_uri="{AUTH_SERVER_URI}"'
                ),
                "Content-Type": "application/json"
            }
        )
        await response(scope, receive, send)