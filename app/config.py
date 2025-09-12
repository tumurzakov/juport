"""Application configuration."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str = "mysql+aiomysql://user:password@localhost:3306/juport"
    
    # Jupyter Lab
    jupyter_notebooks_path: str = "/app/notebooks"
    jupyter_output_path: str = "/app/outputs"
    
    # Application
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = "your-secret-key-here"
    
    # Scheduler
    scheduler_interval: int = 60  # seconds
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
