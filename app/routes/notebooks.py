"""Notebook management API routes."""
from typing import List
from litestar import Controller, get
from app.services.notebook_executor import NotebookExecutor
from app.schemas import NotebookInfo


class NotebooksController(Controller):
    """Controller for notebook management."""
    
    path = "/api/notebooks"
    
    @get("/")
    async def get_notebooks(self) -> List[NotebookInfo]:
        """Get list of available notebooks."""
        executor = NotebookExecutor()
        notebooks = await executor.get_notebook_list()
        
        return [
            NotebookInfo(
                name=notebook["name"],
                path=notebook["path"],
                size=notebook["size"],
                modified=notebook["modified"]
            )
            for notebook in notebooks
        ]
