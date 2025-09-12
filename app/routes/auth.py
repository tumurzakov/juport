"""Authentication routes."""
import logging
import secrets
from typing import Optional
from litestar import Controller, post, get, Request
from litestar.response import Template, Response, Redirect
from litestar.exceptions import ValidationException
from app.services.auth import auth_service
from app.config import settings

logger = logging.getLogger(__name__)


class AuthController(Controller):
    """Controller for authentication."""
    
    path = "/auth"
    
    @get("/login")
    async def login_page(self, request: Request) -> Template:
        """Show login page."""
        # If LDAP is not configured, redirect to main page
        if not auth_service.is_ldap_enabled():
            return Redirect("/")
        
        return Template(
            template_name="login.html",
            context={
                "request": request,
                "ldap_enabled": True
            }
        )
    
    @post("/login")
    async def login(self, request: Request) -> Response:
        """Handle login form submission."""
        # If LDAP is not configured, redirect to main page
        if not auth_service.is_ldap_enabled():
            return Redirect("/")
        
        try:
            form_data = await request.form()
            username = form_data.get("username", "").strip()
            password = form_data.get("password", "").strip()
            
            if not username:
                return Template(
                    template_name="login.html",
                    context={
                        "request": request,
                        "ldap_enabled": True,
                        "error": "Username is required"
                    }
                )
            
            # Authenticate user
            user_info = auth_service.authenticate(username, password)
            
            if not user_info or not user_info.get("authenticated"):
                return Template(
                    template_name="login.html",
                    context={
                        "request": request,
                        "ldap_enabled": True,
                        "error": "Invalid username or password"
                    }
                )
            
            # Create session
            session_id = secrets.token_urlsafe(32)
            
            # Set session cookie and redirect
            response = Redirect("/")
            response.set_cookie(
                "session_id",
                session_id,
                max_age=86400,  # 24 hours
                httponly=True,
                secure=not settings.debug,
                samesite="lax"
            )
            
            logger.info(f"User {username} logged in successfully")
            return response
            
        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            return Template(
                template_name="login.html",
                context={
                    "request": request,
                    "ldap_enabled": True,
                    "error": f"An error occurred during login: {str(e)}"
                }
            )
    
    @get("/logout")
    async def logout(self, request: Request) -> Response:
        """Handle logout."""
        response = Redirect("/")
        response.delete_cookie("session_id")
        logger.info("User logged out")
        return response
