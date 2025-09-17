"""Notebook execution service."""
import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class NotebookExecutor:
    """Service for executing Jupyter notebooks."""

    def __init__(self):
        self.notebooks_path = Path(settings.jupyter_notebooks_path)
        self.output_path = Path(settings.jupyter_output_path)
        self.reports_output_path = self.output_path / "reports"
        self.executions_output_path = self.output_path / "executions"

        # Ensure output directories exist
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.reports_output_path.mkdir(parents=True, exist_ok=True)
        self.executions_output_path.mkdir(parents=True, exist_ok=True)

    async def execute_notebook(
        self,
        notebook_path: str,
        variables: Dict[str, Any],
        artifacts_config: Dict[str, Any],
        task_id: Optional[int] = None,
        execution_datetime: Optional[str] = None
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

        # Create permanent execution directory with hierarchical structure
        report_name = full_notebook_path.stem
        if execution_datetime is None:
            execution_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        execution_output_dir = self.executions_output_path / report_name / execution_datetime
        execution_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created execution directory: {execution_output_dir}")

        # Create temporary directory in system temp directory for notebook execution
        temp_execution_dir = Path(tempfile.mkdtemp(prefix=f"juport_{execution_id}_"))
        logger.info(f"Created temporary execution directory: {temp_execution_dir}")

        # Create permanent report directory (for backward compatibility)
        report_output_dir = self.reports_output_path / report_name
        report_output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Copy notebook to temporary directory and add warning suppression
            temp_notebook_path = self._copy_notebook_to_temp_dir(full_notebook_path, temp_execution_dir, variables)
            logger.info(f"Copied notebook to temporary directory: {temp_notebook_path}")

            # Copy uploaded files to temporary directory if any
            if task_id:
                await self._copy_uploaded_files_to_temp_dir(temp_execution_dir, task_id)

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
            # Collect all artifacts from temporary directory (including uploaded files)
            artifacts = self._collect_artifacts(temp_execution_dir, artifacts_config)

            # Copy all generated files (except .ipynb) to permanent execution directory
            final_artifacts = []
            final_html_path = None

            for artifact in artifacts:
                source_path = Path(artifact["path"])
                if source_path.exists() and source_path.suffix != ".ipynb":
                    # Keep original filename as is
                    final_filename = source_path.name
                    execution_file_path = execution_output_dir / final_filename

                    try:
                        # Copy file to permanent execution location
                        shutil.copy2(source_path, execution_file_path)
                        logger.info(f"Copied artifact: {source_path} -> {execution_file_path}")

                        # Update artifact info with relative path for web access
                        final_artifact = artifact.copy()
                        final_artifact["path"] = f"executions/{report_name}/{execution_datetime}/{final_filename}"
                        final_artifact["name"] = final_filename
                        final_artifacts.append(final_artifact)

                        # Track HTML file
                        if source_path.suffix == ".html":
                            final_html_path = f"executions/{report_name}/{execution_datetime}/{final_filename}"

                    except Exception as e:
                        logger.error(f"Failed to copy artifact {source_path}: {e}")
                        # Don't add to final_artifacts if copy failed

            # Also copy to legacy report directory for backward compatibility
            for artifact in final_artifacts:
                source_path = Path(artifact["path"].replace("executions/", str(self.executions_output_path) + "/"))
                if source_path.exists():
                    legacy_path = report_output_dir / source_path.name
                    try:
                        shutil.copy2(source_path, legacy_path)
                        logger.info(f"Copied to legacy location: {source_path} -> {legacy_path}")
                    except Exception as e:
                        logger.warning(f"Failed to copy to legacy location {legacy_path}: {e}")

            # Prepare result
            result = {
                "html_path": final_html_path,
                "artifacts": final_artifacts,
                "log": stdout.decode() if stdout else "",
                "execution_id": execution_id,
                "output_dir": str(execution_output_dir),
                "execution_datetime": execution_datetime
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

    def _copy_notebook_to_temp_dir(self, notebook_path: Path, temp_dir: Path, variables: dict = None) -> Path:
        """
        Copy notebook to temporary directory and add warning suppression code.
        Also replace Colab parameters and os.getenv() calls with actual values.

        Args:
            notebook_path: Path to the original notebook
            temp_dir: Temporary directory to copy notebook to
            variables: Dictionary of variables to replace in the notebook

        Returns:
            Path to the temporary notebook with warning suppression
        """
        import json

        # Read the original notebook
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)

        # Replace variables in notebook cells if provided
        if variables:
            self._replace_variables_in_notebook(notebook, variables)

        # Create warning suppression and variables loading code cell
        warning_suppression_code = [
            "import warnings\n",
            "warnings.filterwarnings('ignore')\n",
            "import pandas as pd\n",
            "pd.options.mode.chained_assignment = None\n",
            "pd.set_option('mode.chained_assignment', None)\n",
            "import os\n",
            "import json\n",
            "os.environ['PYTHONWARNINGS'] = 'ignore'\n",
            "\n",
            "# Load variables from JUPORT_VARIABLES if available\n",
            "if 'JUPORT_VARIABLES' in os.environ:\n",
            "    try:\n",
            "        juport_vars = json.loads(os.environ['JUPORT_VARIABLES'])\n",
            "        for key, value in juport_vars.items():\n",
            "            os.environ[key] = str(value)\n",
            "    except Exception as e:\n",
            "        print(f'Error loading JUPORT_VARIABLES: {e}')\n"
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

    def _replace_variables_in_notebook(self, notebook: dict, variables: dict):
        """
        Replace variables in notebook cells.

        Args:
            notebook: Notebook dictionary
            variables: Dictionary of variables to replace
        """
        for cell in notebook.get("cells", []):
            if cell.get("cell_type") == "code":
                source = cell.get("source", [])
                if source:
                    # Join source lines and replace variables
                    cell_text = "".join(source)
                    modified_text = self._replace_variables_in_code(cell_text, variables)

                    # Split back into lines
                    cell["source"] = modified_text.splitlines(keepends=True)

    def _replace_variables_in_code(self, code: str, variables: dict) -> str:
        """
        Replace variables in code text.

        Args:
            code: Code text to modify
            variables: Dictionary of variables to replace

        Returns:
            Modified code text
        """
        import re

        lines = code.split('\n')
        modified_lines = []

        for line in lines:
            modified_line = line

            # Replace Colab parameters: variable = 'value' # @param ...
            colab_pattern = r'^(\w+)\s*=\s*([^#\n]+?)\s*#\s*@param'
            match = re.search(colab_pattern, line.strip())
            if match:
                var_name = match.group(1).strip()
                if var_name in variables:
                    # Replace the value part
                    value = variables[var_name]
                    # Format value appropriately based on type
                    if isinstance(value, str):
                        # Check if it's a boolean string
                        if value.lower() in ['true', 'false']:
                            formatted_value = 'True' if value.lower() == 'true' else 'False'
                        # Check if it's None
                        elif value.lower() == 'none':
                            formatted_value = 'None'
                        # Check if it's a number string (but not a date)
                        elif value.replace('.', '').replace('-', '').isdigit() and not re.match(r'\d{4}-\d{2}-\d{2}', value):
                            formatted_value = value
                        # Check if it's a float string (but not a date)
                        elif value.replace('.', '').replace('-', '').replace('e', '').replace('E', '').isdigit() and not re.match(r'\d{4}-\d{2}-\d{2}', value):
                            formatted_value = value
                        # Check if it's a date string (YYYY-MM-DD format)
                        elif re.match(r'\d{4}-\d{2}-\d{2}', value):
                            formatted_value = f'"{value}"'
                        else:
                            # Regular string with quotes
                            formatted_value = f'"{value}"'
                    elif isinstance(value, bool):
                        # Boolean values
                        formatted_value = 'True' if value else 'False'
                    elif isinstance(value, int):
                        # Integer values
                        formatted_value = str(value)
                    elif isinstance(value, float):
                        # Float values
                        formatted_value = str(value)
                    elif value is None:
                        # None values
                        formatted_value = 'None'
                    else:
                        # Default to string representation with quotes
                        formatted_value = f'"{str(value)}"'

                    # Replace the value in the line
                    modified_line = re.sub(
                        r'^(\w+)\s*=\s*([^#\n]+?)\s*#\s*@param',
                        rf'\1 = {formatted_value} # @param',
                        line
                    )

            # Replace os.getenv() calls: os.getenv("VAR_NAME", "default")
            getenv_pattern = r'os\.getenv\([\'"]([^\'"]+)[\'"](?:,\s*[\'"]([^\'"]*)[\'"])?\)'
            def replace_getenv(match):
                var_name = match.group(1)
                if var_name in variables:
                    value = variables[var_name]
                    if isinstance(value, str):
                        return f'"{value}"'
                    else:
                        return str(value)
                return match.group(0)  # Keep original if not found

            modified_line = re.sub(getenv_pattern, replace_getenv, modified_line)

            modified_lines.append(modified_line)

        return '\n'.join(modified_lines)

    async def _copy_uploaded_files_to_temp_dir(self, temp_dir: Path, task_id: int):
        """
        Copy uploaded files to temporary execution directory.

        Args:
            temp_dir: Temporary directory for execution
            task_id: Task ID to find uploaded files
        """
        try:
            # Look for uploaded files with this task_id
            uploads_dir = Path("data/uploads")
            if not uploads_dir.exists():
                logger.info("No uploads directory found, skipping file copy")
                return

            # Find files that match the task pattern
            # Files are stored as task_{task_id}_{original_filename}
            uploaded_files = []
            for file_path in uploads_dir.glob(f"task_{task_id}_*"):
                if file_path.is_file():
                    uploaded_files.append(file_path)

            if not uploaded_files:
                logger.info(f"No uploaded files found for task {task_id}")
                return

            # Copy each uploaded file to temp directory
            for uploaded_file in uploaded_files:
                # Extract original filename (remove task_ prefix, task_id and index)
                original_filename = uploaded_file.name
                if original_filename.startswith(f"task_{task_id}_"):
                    # Remove task_{task_id}_ prefix and index
                    # Format: task_{task_id}_{index}_{original_filename}
                    parts = original_filename.split("_", 3)  # Split into max 4 parts
                    if len(parts) >= 4:
                        original_filename = parts[3]  # Get the original filename
                    else:
                        # Fallback for old format without index
                        original_filename = original_filename[len(f"task_{task_id}_"):]

                dest_path = temp_dir / original_filename
                shutil.copy2(uploaded_file, dest_path)
                logger.info(f"Copied uploaded file: {uploaded_file} -> {dest_path}")

            logger.info(f"Copied {len(uploaded_files)} uploaded files to temp directory")

        except Exception as e:
            logger.error(f"Error copying uploaded files: {e}")
            # Don't raise exception, just log the error
            # This allows execution to continue even if file copy fails

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
        Collect all artifacts from output directory (including uploaded files).

        Args:
            output_dir: Directory where artifacts were generated
            artifacts_config: Configuration for expected artifacts

        Returns:
            List of artifact information
        """
        artifacts = []

        # Collect ALL files from output directory (except .ipynb files)
        for file_path in output_dir.iterdir():
            if file_path.is_file() and file_path.suffix != ".ipynb":
                # Determine file type and description
                file_type = "file"
                description = f"File: {file_path.name}"

                # Check if it's a common output file type
                if file_path.suffix.lower() in [".xlsx", ".xls", ".csv", ".json", ".pdf", ".html", ".png", ".jpg", ".jpeg"]:
                    file_type = "generated_file"
                    description = f"Generated {file_path.suffix[1:].upper()} file"
                elif file_path.suffix.lower() in [".txt", ".log", ".out"]:
                    file_type = "output_file"
                    description = f"Output file: {file_path.name}"
                else:
                    file_type = "uploaded_file"
                    description = f"Uploaded file: {file_path.name}"

                artifacts.append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "type": file_type,
                    "description": description
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

    def scan_notebook_variables(self, notebook_path: str) -> List[Dict[str, str]]:
        """
        Scan notebook for os.getenv() calls and Colab @param annotations.

        Args:
            notebook_path: Path to the notebook file

        Returns:
            List of variable information with name, default_value, and description
        """
        import json

        variables = []

        try:
            full_notebook_path = self.notebooks_path / notebook_path

            if not full_notebook_path.exists():
                logger.warning(f"Notebook not found: {full_notebook_path}")
                return variables

            with open(full_notebook_path, 'r', encoding='utf-8') as f:
                notebook = json.load(f)

            for cell in notebook.get("cells", []):
                if cell.get("cell_type") == "code":
                    source = cell.get("source", [])
                    cell_text = "".join(source)

                    # Scan for os.getenv() calls
                    self._scan_os_getenv_variables(cell_text, variables)

                    # Scan for Colab @param annotations
                    self._scan_colab_params(cell_text, variables)

            logger.info(f"Found {len(variables)} variables in notebook {notebook_path}: {[v['name'] for v in variables]}")

        except Exception as e:
            logger.error(f"Error scanning notebook {notebook_path} for variables: {e}")

        return variables

    def _scan_os_getenv_variables(self, cell_text: str, variables: List[Dict[str, str]]):
        """Scan for os.getenv() calls in cell text."""
        # Pattern to match os.getenv() calls
        # Matches: os.getenv("VAR_NAME"), os.getenv("VAR_NAME", "default"), os.getenv('VAR_NAME', 'default')
        getenv_pattern = r'os\.getenv\([\'"]([^\'"]+)[\'"](?:,\s*[\'"]([^\'"]*)[\'"])?\)'

        matches = re.findall(getenv_pattern, cell_text)

        for match in matches:
            var_name = match[0]
            default_value = match[1] if match[1] else ""

            # Skip if we already have this variable
            if not any(v["name"] == var_name for v in variables):
                # Try to find a comment or description for this variable
                description = self._extract_variable_description(cell_text, var_name)

                variables.append({
                    "name": var_name,
                    "default_value": default_value,
                    "description": description,
                    "type": self._guess_variable_type(default_value),
                    "source": "os.getenv"
                })

    def _scan_colab_params(self, cell_text: str, variables: List[Dict[str, str]]):
        """Scan for Colab @param annotations in cell text."""
        # Pattern to match Colab @param annotations
        # Matches: variable = 'value' # @param {type:"string"} or variable = 'value' # @param ["option1", "option2"]
        colab_pattern = r'^(\w+)\s*=\s*([^#\n]+?)\s*#\s*@param\s*(.+?)(?:\s*$|\s*\{)'

        lines = cell_text.split('\n')
        for line in lines:
            match = re.search(colab_pattern, line.strip())
            if match:
                var_name = match.group(1).strip()
                default_value = match.group(2).strip().strip('\'"')
                param_part = match.group(3).strip()

                # Skip if we already have this variable
                if not any(v["name"] == var_name for v in variables):
                    # Parse param configuration
                    param_info = self._parse_colab_param(param_part, default_value, line)

                    variables.append({
                        "name": var_name,
                        "default_value": default_value,
                        "description": param_info.get("description", f"Colab parameter: {var_name}"),
                        "type": param_info.get("type", "text"),
                        "source": "colab_param",
                        "colab_config": param_info
                    })

    def _parse_colab_param(self, param_config: str, default_value: str, original_line: str = "") -> Dict[str, Any]:
        """Parse Colab @param configuration."""
        import json

        try:
            config_str = param_config.strip()

            # Check if it's a simple dropdown list (starts with [)
            if config_str.startswith('[') and config_str.endswith(']'):
                # Simple dropdown list
                options_str = config_str[1:-1]  # Remove brackets
                options = [opt.strip().strip('\'"') for opt in options_str.split(',')]

                return {
                    "type": "dropdown",
                    "original_type": "dropdown",
                    "options": options,
                    "description": ""
                }

            # JSON configuration
            if not config_str.startswith('{'):
                config_str = '{' + config_str + '}'

            # Try to fix common JSON issues
            config_str = config_str.replace("'", '"')  # Replace single quotes with double quotes

            # Fix unquoted keys (common in Colab @param)
            import re
            config_str = re.sub(r'(\w+):', r'"\1":', config_str)

            # Parse the configuration
            config = json.loads(config_str)

            # Determine type and additional options
            param_type = config.get("type", "string")

            # Map Colab types to our types
            type_mapping = {
                "string": "text",
                "number": "number",
                "integer": "number",
                "boolean": "boolean",
                "date": "date",
                "raw": "text",
                "dropdown": "dropdown"
            }

            mapped_type = type_mapping.get(param_type, "text")

            # Handle special cases
            if param_type == "slider":
                if "min" in config and "max" in config:
                    mapped_type = "range"
                else:
                    mapped_type = "number"

            # Extract options for dropdown
            options = []
            if "[" in original_line and "]" in original_line:
                # Extract dropdown options from the original line
                options_match = re.search(r'\[([^\]]+)\]', original_line)
                if options_match:
                    options_str = options_match.group(1)
                    # Parse options (handle both strings and other types)
                    options = [opt.strip().strip('\'"') for opt in options_str.split(',')]

            result = {
                "type": mapped_type,
                "original_type": param_type,
                "options": options,
                "description": config.get("description", "")
            }

            # Add slider-specific properties
            if param_type == "slider":
                result.update({
                    "min": config.get("min", 0),
                    "max": config.get("max", 100),
                    "step": config.get("step", 1)
                })

            # Add placeholder
            if "placeholder" in config:
                result["placeholder"] = config["placeholder"]

            # Add allow-input for text fields
            if "allow-input" in config:
                result["allow_input"] = config["allow-input"]

            return result

        except Exception as e:
            logger.warning(f"Failed to parse Colab param config '{param_config}': {e}")
            return {
                "type": "text",
                "original_type": "unknown",
                "description": ""
            }

    def _extract_variable_description(self, cell_text: str, var_name: str) -> str:
        """Extract description for a variable from cell text."""
        # Look for comments near the variable usage
        lines = cell_text.split('\n')

        for i, line in enumerate(lines):
            if var_name in line and 'os.getenv' in line:
                # Check previous lines for comments
                for j in range(max(0, i-3), i):
                    comment_line = lines[j].strip()
                    if comment_line.startswith('#') and '=' not in comment_line:
                        # Extract description from comment
                        description = comment_line[1:].strip()
                        if len(description) > 0:
                            return description

                # Check if there's an inline comment
                if '#' in line:
                    parts = line.split('#', 1)
                    if len(parts) > 1:
                        comment = parts[1].strip()
                        if len(comment) > 0:
                            return comment

        return f"Environment variable: {var_name}"

    def _guess_variable_type(self, default_value: str) -> str:
        """Guess the type of variable based on default value."""
        if not default_value:
            return "text"

        # Try to parse as number
        try:
            float(default_value)
            return "number"
        except ValueError:
            pass

        # Check for boolean-like values
        if default_value.lower() in ['true', 'false', 'yes', 'no', '1', '0']:
            return "boolean"

        # Check for date-like patterns
        if re.match(r'\d{4}-\d{2}-\d{2}', default_value):
            return "date"

        # Check for URL-like patterns
        if default_value.startswith(('http://', 'https://', 'ftp://')):
            return "url"

        # Check for email-like patterns
        if '@' in default_value and '.' in default_value:
            return "email"

        return "text"
