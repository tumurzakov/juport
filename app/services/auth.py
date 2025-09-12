"""Authentication service with LDAP support."""
import logging
from typing import Optional, Dict, Any
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException
from app.config import settings

logger = logging.getLogger(__name__)


class AuthService:
    """Authentication service with LDAP support."""
    
    def __init__(self):
        self.ldap_enabled = bool(settings.ldap_server)
        self.server = None
        if self.ldap_enabled:
            self._setup_ldap_server()
    
    def _setup_ldap_server(self):
        """Setup LDAP server connection."""
        try:
            self.server = Server(
                settings.ldap_server,
                port=settings.ldap_port,
                use_ssl=settings.ldap_use_ssl,
                get_info=ALL
            )
            logger.info(f"LDAP server configured: {settings.ldap_server}:{settings.ldap_port}")
        except Exception as e:
            logger.error(f"Failed to setup LDAP server: {e}")
            self.ldap_enabled = False
    
    def is_ldap_enabled(self) -> bool:
        """Check if LDAP authentication is enabled."""
        return self.ldap_enabled
    
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with LDAP or allow access without authentication.
        
        Args:
            username: Username to authenticate
            password: Password to authenticate
            
        Returns:
            User info dict if authentication successful, None otherwise
        """
        if not self.ldap_enabled:
            # No LDAP configured, allow access without authentication
            logger.info(f"LDAP not configured, allowing access for user: {username}")
            return {
                "username": username,
                "authenticated": True,
                "method": "no_auth"
            }
        
        return self._ldap_authenticate(username, password)
    
    def _ldap_authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with LDAP.
        
        Args:
            username: Username to authenticate
            password: Password to authenticate
            
        Returns:
            User info dict if authentication successful, None otherwise
        """
        if not self.server:
            logger.error("LDAP server not configured")
            return None
        
        try:
            # Method 1: Direct bind with user DN template
            if settings.ldap_user_dn_template:
                user_dn = settings.ldap_user_dn_template.format(username=username)
                return self._direct_bind_auth(user_dn, password, username)
            
            # Method 2: Search and bind
            if settings.ldap_user_search_base and settings.ldap_user_search_filter:
                return self._search_bind_auth(username, password)
            
            logger.error("LDAP configuration incomplete: missing user_dn_template or user_search settings")
            return None
            
        except Exception as e:
            logger.error(f"LDAP authentication failed for user {username}: {e}")
            return None
    
    def _direct_bind_auth(self, user_dn: str, password: str, username: str) -> Optional[Dict[str, Any]]:
        """Authenticate using direct bind with user DN template."""
        try:
            conn = Connection(
                self.server,
                user=user_dn,
                password=password,
                auto_bind=True
            )
            
            # Get user attributes
            user_info = self._get_user_info(conn, user_dn, username)
            conn.unbind()
            
            return user_info
            
        except LDAPException as e:
            logger.warning(f"Direct bind authentication failed for {username}: {e}")
            return None
    
    def _search_bind_auth(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate using search and bind method."""
        try:
            # First, bind with service account to search for user
            service_conn = None
            if settings.ldap_bind_dn and settings.ldap_bind_password:
                service_conn = Connection(
                    self.server,
                    user=settings.ldap_bind_dn,
                    password=settings.ldap_bind_password,
                    auto_bind=True
                )
            else:
                # Anonymous bind
                service_conn = Connection(self.server, auto_bind=True)
            
            # Search for user
            search_filter = settings.ldap_user_search_filter.format(username=username)
            service_conn.search(
                search_base=settings.ldap_user_search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['*']
            )
            
            if not service_conn.entries:
                logger.warning(f"User {username} not found in LDAP")
                service_conn.unbind()
                return None
            
            user_entry = service_conn.entries[0]
            user_dn = str(user_entry.entry_dn)
            service_conn.unbind()
            
            # Now authenticate the user
            user_conn = Connection(
                self.server,
                user=user_dn,
                password=password,
                auto_bind=True
            )
            
            user_info = self._get_user_info(user_conn, user_dn, username)
            user_conn.unbind()
            
            return user_info
            
        except LDAPException as e:
            logger.warning(f"Search bind authentication failed for {username}: {e}")
            return None
    
    def _get_user_info(self, conn: Connection, user_dn: str, username: str) -> Dict[str, Any]:
        """Get user information from LDAP."""
        try:
            # Get user attributes
            conn.search(
                search_base=user_dn,
                search_filter='(objectClass=*)',
                search_scope=SUBTREE,
                attributes=['*']
            )
            
            user_attrs = {}
            if conn.entries:
                entry = conn.entries[0]
                for attr in entry.entry_attributes:
                    values = entry[attr].values
                    if len(values) == 1:
                        user_attrs[attr] = values[0]
                    else:
                        user_attrs[attr] = values
            
            # Get user groups if configured
            groups = []
            if settings.ldap_group_search_base and settings.ldap_group_search_filter:
                groups = self._get_user_groups(conn, user_dn)
            
            return {
                "username": username,
                "dn": user_dn,
                "authenticated": True,
                "method": "ldap",
                "attributes": user_attrs,
                "groups": groups
            }
            
        except Exception as e:
            logger.error(f"Failed to get user info for {username}: {e}")
            return {
                "username": username,
                "dn": user_dn,
                "authenticated": True,
                "method": "ldap",
                "attributes": {},
                "groups": []
            }
    
    def _get_user_groups(self, conn: Connection, user_dn: str) -> list:
        """Get user groups from LDAP."""
        try:
            search_filter = settings.ldap_group_search_filter.format(user_dn=user_dn)
            conn.search(
                search_base=settings.ldap_group_search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['cn', 'name']
            )
            
            groups = []
            for entry in conn.entries:
                if 'cn' in entry:
                    groups.append(str(entry.cn))
                elif 'name' in entry:
                    groups.append(str(entry.name))
            
            return groups
            
        except Exception as e:
            logger.error(f"Failed to get user groups: {e}")
            return []


# Global auth service instance
auth_service = AuthService()
