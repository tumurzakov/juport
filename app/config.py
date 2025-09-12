"""Application configuration."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str = "mysql+aiomysql://user:password@localhost:3306/juport"
    
    # Jupyter Lab
    jupyter_notebooks_path: str = "data/notebooks"
    jupyter_output_path: str = "data/outputs"
    
    # Application
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = "your-secret-key-here"
    
    # Scheduler
    scheduler_interval: int = 60  # seconds
    
    # LDAP Authentication (optional)
    ldap_server: Optional[str] = None
    ldap_port: int = 389
    ldap_use_ssl: bool = False
    ldap_base_dn: Optional[str] = None
    ldap_user_dn_template: Optional[str] = None
    ldap_bind_dn: Optional[str] = None
    ldap_bind_password: Optional[str] = None
    ldap_user_search_base: Optional[str] = None
    ldap_user_search_filter: Optional[str] = None
    ldap_group_search_base: Optional[str] = None
    ldap_group_search_filter: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
