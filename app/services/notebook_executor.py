"""Notebook execution service."""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from app.config import settings

logger = logging.getLogger(__name__)


class NotebookExecutor:
    """Service for executing Jupyter notebooks."""
    
    def __init__(self):
        self.notebooks_path = Path(settings.jupyter_notebooks_path)
        self.output_path = Path(settings.jupyter_output_path)
        self.reports_output_path = self.output_path / "reports"
        
        # Ensure output directories exist
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.reports_output_path.mkdir(parents=True, exist_ok=True)
    
    async def execute_notebook(
        self, 
        notebook_path: str, 
        variables: Dict[str, Any],
        artifacts_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a Jupyter notebook and return results.
        
        Args:
            notebook_path: Path to the notebook file
            variables: Variables to pass to the notebook
            artifacts_config: Configuration for output artifacts
            
        Returns:
            Dictionary with execution results
        """
        logger.info(f"Executing notebook: {notebook_path}")
        
        # Full path to notebook
        full_notebook_path = self.notebooks_path / notebook_path
        
        if not full_notebook_path.exists():
            raise FileNotFoundError(f"Notebook not found: {full_notebook_path}")
        
        # Create a temporary copy of the notebook with warning suppression
        temp_notebook_path = self._create_notebook_with_warnings_suppressed(full_notebook_path)
        
        # Create execution timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        execution_id = f"{full_notebook_path.stem}_{timestamp}"
        
        # Create temporary directory for execution
        temp_execution_dir = self.output_path / f"temp_{execution_id}"
        temp_execution_dir.mkdir(parents=True, exist_ok=True)
        
        # Create permanent report directory
        report_name = full_notebook_path.stem
        report_output_dir = self.reports_output_path / report_name
        report_output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Prepare environment variables for the notebook
            env = os.environ.copy()
            env.update({
                "JUPORT_VARIABLES": json.dumps(variables),
                "JUPORT_ARTIFACTS_CONFIG": json.dumps(artifacts_config),
                "JUPORT_OUTPUT_DIR": str(temp_execution_dir),
                "JUPORT_EXECUTION_ID": execution_id,
                "PYTHONWARNINGS": "ignore",
                "TF_CPP_MIN_LOG_LEVEL": "3"
            })
            
            # Execute notebook using nbconvert
            html_output_path = temp_execution_dir / f"{full_notebook_path.stem}.html"
            
            cmd = [
                "jupyter", "nbconvert",
                str(temp_notebook_path),
                "--to", "html",
                "--no-input",
                f"--output={html_output_path}",
                "--ExecutePreprocessor.enabled=True",
                "--ExecutePreprocessor.timeout=3600",
                "--ExecutePreprocessor.allow_errors=True",
                "--ExecutePreprocessor.raise_on_iopub_timeout=False"
            ]
            
            logger.info(f"Running command: {' '.join(cmd)}")
            
            # Run the command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.notebooks_path)
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Notebook execution failed: {error_msg}")
                raise RuntimeError(f"Notebook execution failed: {error_msg}")
            
            # Collect artifacts from both temporary directory and notebooks directory
            artifacts = self._collect_artifacts(temp_execution_dir, artifacts_config)
            
            # Also collect artifacts from notebooks directory (where notebook was executed)
            notebook_artifacts = self._collect_artifacts(self.notebooks_path, artifacts_config)
            
            # Merge artifacts, avoiding duplicates
            for artifact in notebook_artifacts:
                if not any(art["name"] == artifact["name"] for art in artifacts):
                    artifacts.append(artifact)
            
            # Copy all generated files to permanent report directory
            final_artifacts = []
            final_html_path = None
            
            for artifact in artifacts:
                source_path = Path(artifact["path"])
                if source_path.exists():
                    # Create unique filename with timestamp
                    timestamp_suffix = datetime.now().strftime("_%Y%m%d_%H%M%S")
                    file_extension = source_path.suffix
                    file_stem = source_path.stem
                    final_filename = f"{file_stem}{timestamp_suffix}{file_extension}"
                    final_path = report_output_dir / final_filename
                    
                    # Copy file to permanent location
                    shutil.copy2(source_path, final_path)
                    
                    # Update artifact info
                    final_artifact = artifact.copy()
                    final_artifact["path"] = str(final_path)
                    final_artifact["name"] = final_filename
                    final_artifacts.append(final_artifact)
                    
                    # Track HTML file
                    if source_path.suffix == ".html":
                        final_html_path = str(final_path)
                    
                    # Clean up source file if it's in notebooks directory (not temp directory)
                    if str(source_path).startswith(str(self.notebooks_path)) and source_path.suffix != ".ipynb":
                        try:
                            source_path.unlink()
                            logger.info(f"Cleaned up generated file: {source_path}")
                        except Exception as e:
                            logger.warning(f"Failed to clean up file {source_path}: {e}")
            
            # Prepare result
            result = {
                "html_path": final_html_path,
                "artifacts": final_artifacts,
                "log": stdout.decode() if stdout else "",
                "execution_id": execution_id,
                "output_dir": str(report_output_dir)
            }
            
            logger.info(f"Notebook execution completed: {execution_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error executing notebook {notebook_path}: {e}")
            raise
        finally:
            # Clean up temporary directory and notebook
            if temp_execution_dir.exists():
                shutil.rmtree(temp_execution_dir)
                logger.info(f"Cleaned up temporary directory: {temp_execution_dir}")
            if temp_notebook_path.exists():
                temp_notebook_path.unlink()
                logger.info(f"Cleaned up temporary notebook: {temp_notebook_path}")
    
    def _create_notebook_with_warnings_suppressed(self, notebook_path: Path) -> Path:
        """
        Create a temporary copy of the notebook with warning suppression code added.
        
        Args:
            notebook_path: Path to the original notebook
            
        Returns:
            Path to the temporary notebook with warning suppression
        """
        import json
        import tempfile
        
        # Read the original notebook
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        
        # Create warning suppression code cell
        warning_suppression_code = [
            "import warnings\n",
            "warnings.filterwarnings('ignore')\n",
            "import pandas as pd\n",
            "pd.options.mode.chained_assignment = None\n",
            "pd.set_option('mode.chained_assignment', None)\n",
            "import os\n",
            "os.environ['PYTHONWARNINGS'] = 'ignore'\n"
        ]
        
        # Create a new cell with warning suppression
        warning_cell = {
            "cell_type": "code",
            "execution_count": None,
            "id": "warning_suppression_cell",
            "metadata": {},
            "outputs": [],
            "source": warning_suppression_code
        }
        
        # Insert the warning suppression cell at the beginning
        notebook["cells"].insert(0, warning_cell)
        
        # Create temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.ipynb', prefix='temp_notebook_')
        os.close(temp_fd)
        
        # Write the modified notebook
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)
        
        return Path(temp_path)
    
    def _collect_artifacts(
        self, 
        output_dir: Path, 
        artifacts_config: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """
        Collect generated artifacts based on configuration.
        
        Args:
            output_dir: Directory where artifacts were generated
            artifacts_config: Configuration for expected artifacts
            
        Returns:
            List of artifact information
        """
        artifacts = []
        
        # Look for configured artifacts
        if "files" in artifacts_config:
            for file_config in artifacts_config["files"]:
                file_path = output_dir / file_config["name"]
                if file_path.exists():
                    artifacts.append({
                        "name": file_config["name"],
                        "path": str(file_path),
                        "type": file_config.get("type", "file"),
                        "description": file_config.get("description", "")
                    })
        
        # Also look for common output files (Excel, CSV, HTML, etc.)
        common_patterns = ["*.xlsx", "*.xls", "*.csv", "*.json", "*.pdf", "*.html"]
        for pattern in common_patterns:
            for file_path in output_dir.glob(pattern):
                if not any(art["path"] == str(file_path) for art in artifacts):
                    artifacts.append({
                        "name": file_path.name,
                        "path": str(file_path),
                        "type": "file",
                        "description": f"Generated {file_path.suffix[1:].upper()} file"
                    })
        
        return artifacts
    
    async def get_notebook_list(self) -> List[Dict[str, str]]:
        """Get list of available notebooks."""
        notebooks = []
        
        if not self.notebooks_path.exists():
            return notebooks
        
        for notebook_path in self.notebooks_path.rglob("*.ipynb"):
            # Skip notebooks in .ipynb_checkpoints directories
            if ".ipynb_checkpoints" in str(notebook_path):
                continue
                
            relative_path = notebook_path.relative_to(self.notebooks_path)
            notebooks.append({
                "name": notebook_path.stem,
                "path": str(relative_path),
                "size": notebook_path.stat().st_size,
                "modified": datetime.fromtimestamp(notebook_path.stat().st_mtime)
            })
        
        return notebooks
    
    async def get_reports_list(self) -> List[Dict[str, Any]]:
        """Get list of available reports (notebooks that can be executed)."""
        reports = []
        
        if not self.notebooks_path.exists():
            return reports
        
        for notebook_path in self.notebooks_path.rglob("*.ipynb"):
            # Skip notebooks in .ipynb_checkpoints directories
            if ".ipynb_checkpoints" in str(notebook_path):
                continue
                
            relative_path = notebook_path.relative_to(self.notebooks_path)
            
            # Check if report output directory exists
            report_name = notebook_path.stem
            report_output_dir = self.reports_output_path / report_name
            
            # Get latest execution info
            latest_execution = None
            if report_output_dir.exists():
                html_files = list(report_output_dir.glob("*.html"))
                if html_files:
                    # Get the most recent HTML file
                    latest_html = max(html_files, key=lambda f: f.stat().st_mtime)
                    latest_execution = {
                        "html_path": str(latest_html),
                        "executed_at": datetime.fromtimestamp(latest_html.stat().st_mtime)
                    }
            
            reports.append({
                "name": notebook_path.stem,
                "path": str(relative_path),
                "size": notebook_path.stat().st_size,
                "modified": datetime.fromtimestamp(notebook_path.stat().st_mtime),
                "latest_execution": latest_execution,
                "has_output": report_output_dir.exists() and any(report_output_dir.iterdir())
            })
        
        return reports
