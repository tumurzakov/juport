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
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Download request for file_path: {file_path}")
        logger.info(f"jupyter_output_path: {settings.jupyter_output_path}")
        
        # Security: prevent directory traversal
        if ".." in file_path or file_path.startswith("/"):
            logger.warning(f"Security violation: {file_path}")
            raise NotFoundException("File not found")
        
        # Construct full path
        full_path = Path(settings.jupyter_output_path) / file_path
        logger.info(f"Full path: {full_path}")
        logger.info(f"Full path exists: {full_path.exists()}")
        logger.info(f"Full path is file: {full_path.is_file()}")
        
        # Check if file exists and is within output directory
        if not full_path.exists() or not full_path.is_file():
            logger.warning(f"File not found: {full_path}")
            raise NotFoundException("File not found")
        
        # Ensure file is within the output directory
        try:
            full_path.resolve().relative_to(Path(settings.jupyter_output_path).resolve())
        except ValueError:
            logger.warning(f"File outside output directory: {full_path}")
            raise NotFoundException("File not found")
        
        logger.info(f"Serving file: {full_path}")
        return File(
            path=str(full_path),
            filename=full_path.name,
            media_type="application/octet-stream"
        )
    
    @get("/executions/{report_name:str}/{execution_date:str}/{filename:str}")
    async def download_execution_file(self, report_name: str, execution_date: str, filename: str) -> File:
        """Download a file from execution directory."""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Download execution file: {report_name}/{execution_date}/{filename}")
        
        # Construct full path
        full_path = Path(settings.jupyter_output_path) / "executions" / report_name / execution_date / filename
        logger.info(f"Full path: {full_path}")
        logger.info(f"Full path exists: {full_path.exists()}")
        logger.info(f"Full path is file: {full_path.is_file()}")
        
        # Check if file exists and is within output directory
        if not full_path.exists() or not full_path.is_file():
            logger.warning(f"File not found: {full_path}")
            raise NotFoundException("File not found")
        
        # Ensure file is within the output directory
        try:
            full_path.resolve().relative_to(Path(settings.jupyter_output_path).resolve())
        except ValueError:
            logger.warning(f"File outside output directory: {full_path}")
            raise NotFoundException("File not found")
        
        logger.info(f"Serving file: {full_path}")
        return File(
            path=str(full_path),
            filename=filename,
            media_type="application/octet-stream"
        )
