"""File serving routes."""
import os
from pathlib import Path
from litestar import Controller, get
from litestar.exceptions import NotFoundException
from litestar.response import File
from app.config import settings


class FilesController(Controller):
    """Controller for serving generated files."""
    
    path = "/api/files"
    
    @get("/{file_path:str}")
    async def download_file(self, file_path: str) -> File:
        """Download a generated file."""
        # Security: prevent directory traversal
        if ".." in file_path or file_path.startswith("/"):
            raise NotFoundException("File not found")
        
        # Construct full path
        full_path = Path(settings.jupyter_output_path) / file_path
        
        # Check if file exists and is within output directory
        if not full_path.exists() or not full_path.is_file():
            raise NotFoundException("File not found")
        
        # Ensure file is within the output directory
        try:
            full_path.resolve().relative_to(Path(settings.jupyter_output_path).resolve())
        except ValueError:
            raise NotFoundException("File not found")
        
        return File(
            path=str(full_path),
            filename=full_path.name,
            media_type="application/octet-stream"
        )
