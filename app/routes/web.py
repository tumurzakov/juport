"""Web interface routes."""
from datetime import datetime
from typing import List
from litestar import Controller, get, Request
from litestar.response import Template, Response, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from app.database import get_db_session
from app.models import Report, ReportExecution, Schedule, ScheduleExecution, Task
from app.services.notebook_executor import NotebookExecutor


class WebController(Controller):
    """Controller for web interface."""
    
    path = "/"
    
    def __init__(self, owner=None):
        super().__init__(owner)
        self.notebook_executor = NotebookExecutor()
    
    @get("/")
    async def index(
        self,
        request: Request,
        db_session: AsyncSession
    ) -> Template:
        """Main page with list of reports."""
        # Get all reports sorted by last execution date (most recent first)
        # Reports without executions will be sorted by creation date
        from sqlalchemy import func, case
        
        result = await db_session.execute(
            select(Report)
            .outerjoin(ReportExecution)
            .options(selectinload(Report.executions))
            .group_by(Report.id)
            .order_by(
                desc(func.max(ReportExecution.completed_at)),
                desc(Report.created_at)
            )
        )
        reports = result.scalars().all()
        
        return Template(
            template_name="index.html",
            context={
                "reports": reports,
                "request": request
            }
        )
    
    @get("/report/{report_id:int}")
    async def view_report(
        self,
        report_id: int,
        request: Request,
        db_session: AsyncSession
    ) -> Template:
        """View specific report with its executions."""
        # Get report with executions
        result = await db_session.execute(
            select(Report)
            .where(Report.id == report_id)
            .options(selectinload(Report.executions))
        )
        report = result.scalar_one_or_none()
        
        if not report:
            return Template(
                template_name="error.html",
                context={
                    "error": "Report not found",
                    "request": request
                }
            )
        
        return Template(
            template_name="report.html",
            context={
                "report": report,
                "request": request
            }
        )
    
    @get("/execution/{execution_id:int}")
    async def view_execution(
        self,
        execution_id: int,
        request: Request,
        db_session: AsyncSession
    ) -> Template:
        """View specific execution result."""
        result = await db_session.execute(
            select(ReportExecution)
            .where(ReportExecution.id == execution_id)
            .options(selectinload(ReportExecution.report))
        )
        execution = result.scalar_one_or_none()
        
        if not execution:
            return Template(
                template_name="error.html",
                context={
                    "error": "Execution not found",
                    "request": request
                }
            )
        
        # Read HTML content if available
        html_content = None
        if execution.html_output_path:
            try:
                # Check if it's a relative path (new format)
                if execution.html_output_path.startswith("executions/"):
                    html_file_path = self.notebook_executor.output_path / execution.html_output_path
                else:
                    # Legacy absolute path
                    html_file_path = Path(execution.html_output_path)
                
                if html_file_path.exists():
                    with open(html_file_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                else:
                    html_content = f"HTML file not found: {html_file_path}"
            except Exception as e:
                html_content = f"Error reading HTML file: {str(e)}"
        
        return Template(
            template_name="execution.html",
            context={
                "execution": execution,
                "html_content": html_content,
                "request": request
            }
        )
    
    @get("/notebooks")
    async def notebooks_list(
        self,
        request: Request
    ) -> Template:
        """List all available notebooks."""
        # Get list of available notebooks
        reports = await self.notebook_executor.get_reports_list()
        
        return Template(
            template_name="notebooks.html",
            context={
                "reports": reports,
                "request": request
            }
        )
    
    @get("/view-report/{report_name:str}")
    async def view_report_result(
        self,
        report_name: str,
        request: Request
    ) -> Template:
        """View the latest execution result of a report."""
        from pathlib import Path
        
        # First try to find in executions directory (new structure)
        executions_dir = self.notebook_executor.executions_output_path / report_name
        report_output_dir = None
        html_content = None
        all_files = []
        
        if executions_dir.exists():
            # Find the most recent execution directory
            execution_dirs = [d for d in executions_dir.iterdir() if d.is_dir()]
            if execution_dirs:
                # Sort by date (most recent first)
                execution_dirs.sort(key=lambda x: x.name, reverse=True)
                latest_execution_dir = execution_dirs[0]
                
                # Find HTML files in the latest execution
                html_files = list(latest_execution_dir.glob("*.html"))
                if html_files:
                    latest_html = max(html_files, key=lambda f: f.stat().st_mtime)
                    try:
                        with open(latest_html, 'r', encoding='utf-8') as f:
                            html_content = f.read()
                    except Exception as e:
                        html_content = f"Error reading HTML file: {str(e)}"
                
                # Get all files in the execution directory
                for file_path in latest_execution_dir.iterdir():
                    if file_path.is_file():
                        all_files.append({
                            "name": file_path.name,
                            "path": f"executions/{report_name}/{latest_execution_dir.name}/{file_path.name}",
                            "size": file_path.stat().st_size,
                            "modified": datetime.fromtimestamp(file_path.stat().st_mtime)
                        })
        
        # Fallback to legacy report output directory
        if not html_content:
            report_output_dir = self.notebook_executor.reports_output_path / report_name
            
            if not report_output_dir.exists():
                return Template(
                    template_name="error.html",
                    context={
                        "error": f"Report '{report_name}' not found or never executed",
                        "request": request
                    }
                )
            
            # Find the latest HTML file
            html_files = list(report_output_dir.glob("*.html"))
            if not html_files:
                return Template(
                    template_name="error.html",
                    context={
                        "error": f"No HTML output found for report '{report_name}'",
                        "request": request
                    }
                )
            
            # Get the most recent HTML file
            latest_html = max(html_files, key=lambda f: f.stat().st_mtime)
            
            # Read HTML content
            try:
                with open(latest_html, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            except Exception as e:
                html_content = f"Error reading HTML file: {str(e)}"
            
            # Get all files in the report directory
            for file_path in report_output_dir.iterdir():
                if file_path.is_file():
                    all_files.append({
                        "name": file_path.name,
                        "path": str(file_path),
                        "size": file_path.stat().st_size,
                        "modified": datetime.fromtimestamp(file_path.stat().st_mtime)
                    })
        
        return Template(
            template_name="report_result.html",
            context={
                "report_name": report_name,
                "html_content": html_content,
                "files": all_files,
                "request": request
            }
        )
    
    @get("/download/{report_name:str}/{filename:str}")
    async def download_file(
        self,
        report_name: str,
        filename: str
    ) -> File:
        """Download a file from a report output directory."""
        from pathlib import Path
        
        # First try to find in executions directory (new structure)
        executions_dir = self.notebook_executor.executions_output_path / report_name
        if executions_dir.exists():
            # Find the most recent execution directory
            execution_dirs = [d for d in executions_dir.iterdir() if d.is_dir()]
            if execution_dirs:
                # Sort by date (most recent first)
                execution_dirs.sort(key=lambda x: x.name, reverse=True)
                latest_execution_dir = execution_dirs[0]
                file_path = latest_execution_dir / filename
                
                if file_path.exists() and file_path.is_file():
                    # Security check: ensure the file is within the execution directory
                    try:
                        file_path.resolve().relative_to(latest_execution_dir.resolve())
                        return File(
                            path=str(file_path),
                            filename=filename,
                            media_type="application/octet-stream"
                        )
                    except ValueError:
                        pass  # Continue to legacy check
        
        # Fallback to legacy report output directory
        report_output_dir = self.notebook_executor.reports_output_path / report_name
        
        if not report_output_dir.exists():
            raise FileNotFoundError(f"Report '{report_name}' not found")
        
        # Construct file path
        file_path = report_output_dir / filename
        
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"File '{filename}' not found in report '{report_name}'")
        
        # Security check: ensure the file is within the report directory
        try:
            file_path.resolve().relative_to(report_output_dir.resolve())
        except ValueError:
            raise FileNotFoundError("Invalid file path")
        
        return File(
            path=str(file_path),
            filename=filename,
            media_type="application/octet-stream"
        )
    
    @get("/proxy-file/{report_name:str}/{execution_date:str}/{filename:str}")
    async def proxy_file(
        self,
        report_name: str,
        execution_date: str,
        filename: str
    ) -> File:
        """Proxy download for files from execution directory."""
        from pathlib import Path
        
        # Construct file path
        file_path = self.notebook_executor.executions_output_path / report_name / execution_date / filename
        
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"File '{filename}' not found in execution '{execution_date}' for report '{report_name}'")
        
        # Security check: ensure the file is within the executions directory
        try:
            file_path.resolve().relative_to(self.notebook_executor.executions_output_path.resolve())
        except ValueError:
            raise FileNotFoundError("Invalid file path")
        
        return File(
            path=str(file_path),
            filename=filename,
            media_type="application/octet-stream"
        )
    
    @get("/favicon.ico")
    async def favicon(self) -> Response:
        """Handle favicon requests."""
        return Response(content=b"", status_code=204)
    
    @get("/.well-known/appspecific/com.chrome.devtools.json")
    async def chrome_devtools(self) -> Response:
        """Handle Chrome DevTools requests to prevent 404 errors in logs."""
        return Response(content=b"", status_code=204)
    
    @get("/schedules")
    async def schedules_list(
        self,
        request: Request,
        db_session: AsyncSession
    ) -> Template:
        """List all schedules."""
        # Get all schedules with their reports
        result = await db_session.execute(
            select(Schedule)
            .options(selectinload(Schedule.report))
            .order_by(desc(Schedule.created_at))
        )
        schedules = result.scalars().all()
        
        return Template(
            template_name="schedules.html",
            context={
                "schedules": schedules,
                "request": request
            }
        )
    
    @get("/schedule/{schedule_id:int}")
    async def view_schedule(
        self,
        schedule_id: int,
        request: Request,
        db_session: AsyncSession
    ) -> Template:
        """View specific schedule with its executions."""
        # Get schedule with executions and report
        result = await db_session.execute(
            select(Schedule)
            .where(Schedule.id == schedule_id)
            .options(
                selectinload(Schedule.executions),
                selectinload(Schedule.report)
            )
        )
        schedule = result.scalar_one_or_none()
        
        if not schedule:
            return Template(
                template_name="error.html",
                context={
                    "error": "Schedule not found",
                    "request": request
                }
            )
        
        return Template(
            template_name="schedule.html",
            context={
                "schedule": schedule,
                "request": request
            }
        )
    
    @get("/tasks")
    async def tasks_list(
        self,
        request: Request,
        db_session: AsyncSession
    ) -> Template:
        """List all tasks."""
        # Get all tasks with their reports and schedules
        result = await db_session.execute(
            select(Task)
            .options(
                selectinload(Task.report),
                selectinload(Task.schedule)
            )
            .order_by(desc(Task.created_at))
        )
        tasks = result.scalars().all()
        
        return Template(
            template_name="tasks.html",
            context={
                "tasks": tasks,
                "request": request
            }
        )
    
    @get("/task/{task_id:int}")
    async def view_task(
        self,
        task_id: int,
        request: Request,
        db_session: AsyncSession
    ) -> Template:
        """View specific task details."""
        result = await db_session.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.report),
                selectinload(Task.schedule)
            )
        )
        task = result.scalar_one_or_none()
        
        if not task:
            return Template(
                template_name="error.html",
                context={
                    "error": "Task not found",
                    "request": request
                }
            )
        
        return Template(
            template_name="task.html",
            context={
                "task": task,
                "request": request
            }
        )