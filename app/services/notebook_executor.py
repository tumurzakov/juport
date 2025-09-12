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
        
        # Auto-detect artifacts if config is empty
        if not artifacts_config or not artifacts_config.get("files"):
            detected_config = self._detect_artifacts_from_notebook(full_notebook_path)
            if detected_config.get("files"):
                artifacts_config = detected_config
                logger.info(f"Auto-detected artifacts for notebook {notebook_path}: {[f['name'] for f in artifacts_config['files']]}")
        
        # Create execution timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        execution_id = f"{full_notebook_path.stem}_{timestamp}"
        
        # Create temporary directory in system temp directory
        temp_execution_dir = Path(tempfile.mkdtemp(prefix=f"juport_{execution_id}_"))
        logger.info(f"Created temporary execution directory: {temp_execution_dir}")
        
        # Create permanent report directory
        report_name = full_notebook_path.stem
        report_output_dir = self.reports_output_path / report_name
        report_output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Copy notebook to temporary directory and add warning suppression
            temp_notebook_path = self._copy_notebook_to_temp_dir(full_notebook_path, temp_execution_dir)
            logger.info(f"Copied notebook to temporary directory: {temp_notebook_path}")
            
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
            
            # Run the command in the temporary directory so files are created there
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(temp_execution_dir)
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Notebook execution failed: {error_msg}")
                raise RuntimeError(f"Notebook execution failed: {error_msg}")
            
            # Collect artifacts from temporary directory (where notebook was executed)
            artifacts = self._collect_artifacts(temp_execution_dir, artifacts_config)
            
            # Copy all generated files (except .ipynb) to permanent report directory
            final_artifacts = []
            final_html_path = None
            
            for artifact in artifacts:
                source_path = Path(artifact["path"])
                if source_path.exists() and source_path.suffix != ".ipynb":
                    # Create unique filename with timestamp
                    timestamp_suffix = datetime.now().strftime("_%Y%m%d_%H%M%S")
                    file_extension = source_path.suffix
                    file_stem = source_path.stem
                    final_filename = f"{file_stem}{timestamp_suffix}{file_extension}"
                    final_path = report_output_dir / final_filename
                    
                    try:
                        # Copy file to permanent location
                        shutil.copy2(source_path, final_path)
                        logger.info(f"Copied artifact: {source_path} -> {final_path}")
                        
                        # Update artifact info
                        final_artifact = artifact.copy()
                        final_artifact["path"] = str(final_path)
                        final_artifact["name"] = final_filename
                        final_artifacts.append(final_artifact)
                        
                        # Track HTML file
                        if source_path.suffix == ".html":
                            final_html_path = str(final_path)
                            
                    except Exception as e:
                        logger.error(f"Failed to copy artifact {source_path}: {e}")
                        # Don't add to final_artifacts if copy failed
            
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
            # Clean up temporary directory and all its contents
            if temp_execution_dir.exists():
                shutil.rmtree(temp_execution_dir)
                logger.info(f"Cleaned up temporary directory: {temp_execution_dir}")
    
    def _copy_notebook_to_temp_dir(self, notebook_path: Path, temp_dir: Path) -> Path:
        """
        Copy notebook to temporary directory and add warning suppression code.
        
        Args:
            notebook_path: Path to the original notebook
            temp_dir: Temporary directory to copy notebook to
            
        Returns:
            Path to the temporary notebook with warning suppression
        """
        import json
        
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
        
        # Create temporary notebook path in temp directory
        temp_notebook_path = temp_dir / notebook_path.name
        
        # Write the modified notebook
        with open(temp_notebook_path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)
        
        return temp_notebook_path
    
    def _detect_artifacts_from_notebook(self, notebook_path: Path) -> Dict[str, Any]:
        """
        Detect expected artifacts from notebook content.
        
        Args:
            notebook_path: Path to the notebook file
            
        Returns:
            Dictionary with detected artifacts configuration
        """
        import json
        import re
        
        artifacts_config = {"files": []}
        
        try:
            with open(notebook_path, 'r', encoding='utf-8') as f:
                notebook = json.load(f)
            
            # Search for file output patterns in notebook cells
            file_patterns = [
                r'\.to_excel\([\'"]([^\'"]+)[\'"]\)',  # pandas to_excel
                r'\.to_csv\([\'"]([^\'"]+)[\'"]\)',    # pandas to_csv
                r'\.savefig\([\'"]([^\'"]+)[\'"]\)',   # matplotlib savefig
                r'open\([\'"]([^\'"]+)[\'"]',          # file open
                r'with open\([\'"]([^\'"]+)[\'"]',     # with open
            ]
            
            for cell in notebook.get("cells", []):
                if cell.get("cell_type") == "code":
                    source = cell.get("source", [])
                    cell_text = "".join(source)
                    
                    for pattern in file_patterns:
                        matches = re.findall(pattern, cell_text)
                        for match in matches:
                            if match and not match.startswith("/") and not match.startswith("http"):
                                artifacts_config["files"].append({
                                    "name": match,
                                    "type": "file",
                                    "description": f"Generated file detected from notebook"
                                })
            
            # Remove duplicates
            seen = set()
            unique_files = []
            for file_config in artifacts_config["files"]:
                if file_config["name"] not in seen:
                    seen.add(file_config["name"])
                    unique_files.append(file_config)
            artifacts_config["files"] = unique_files
            
            logger.info(f"Detected {len(artifacts_config['files'])} artifacts from notebook: {[f['name'] for f in artifacts_config['files']]}")
            
        except Exception as e:
            logger.warning(f"Failed to detect artifacts from notebook {notebook_path}: {e}")
        
        return artifacts_config
    
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
        
        # Look for configured artifacts first
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
        
        # Look for common output files (Excel, CSV, HTML, etc.)
        # This includes files that might not be in the config
        common_patterns = ["*.xlsx", "*.xls", "*.csv", "*.json", "*.pdf", "*.html", "*.png", "*.jpg", "*.jpeg"]
        for pattern in common_patterns:
            for file_path in output_dir.glob(pattern):
                # Skip notebook files
                if file_path.suffix == ".ipynb":
                    continue
                    
                # Check if we already have this artifact
                if not any(art["path"] == str(file_path) for art in artifacts):
                    artifacts.append({
                        "name": file_path.name,
                        "path": str(file_path),
                        "type": "file",
                        "description": f"Generated {file_path.suffix[1:].upper()} file"
                    })
        
        # Log found artifacts for debugging
        if artifacts:
            logger.info(f"Found {len(artifacts)} artifacts in {output_dir}: {[a['name'] for a in artifacts]}")
        else:
            logger.warning(f"No artifacts found in {output_dir}")
        
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
