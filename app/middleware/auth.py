"""Authentication middleware for Litestar."""
import logging
from typing import Optional
from litestar import Request
from litestar.middleware.base import DefineMiddleware
from app.services.auth import auth_service

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """Authentication middleware that checks for valid session."""
    
    def __init__(self, app, exclude_paths: Optional[list] = None):
        self.app = app
        self.exclude_paths = exclude_paths or [
            "/auth/login",
            "/auth/logout", 
            "/static",
            "/favicon.ico",
            "/.well-known"
        ]
    
    async def __call__(self, scope, receive, send):
        """Process request through authentication middleware."""
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        
        request = Request(scope)
        path = request.url.path
        
        # Skip authentication for excluded paths
        if self._should_skip_auth(path):
            return await self.app(scope, receive, send)
        
        # Skip authentication if LDAP is not configured
        if not auth_service.is_ldap_enabled():
            return await self.app(scope, receive, send)
        
        # Check for valid session
        if not self._is_authenticated(request):
            # Redirect to login page
            await self._send_redirect(scope, receive, send, "/auth/login")
            return
        
        return await self.app(scope, receive, send)
    
    def _should_skip_auth(self, path: str) -> bool:
        """Check if path should skip authentication."""
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return True
        return False
    
    async def _send_redirect(self, scope, receive, send, location: str):
        """Send a redirect response."""
        response_body = b""
        headers = [
            (b"location", location.encode()),
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(response_body)).encode()),
        ]
        
        await send({
            "type": "http.response.start",
            "status": 302,
            "headers": headers,
        })
        
        await send({
            "type": "http.response.body",
            "body": response_body,
        })
    
    def _is_authenticated(self, request: Request) -> bool:
        """Check if user is authenticated."""
        # Check for session cookie or header
        session_id = request.cookies.get("session_id")
        if not session_id:
            return False
        
        # In a real implementation, you would validate the session
        # For now, we'll just check if the cookie exists
        return bool(session_id)
