"""Report management API routes."""
import json
import logging
from datetime import datetime
from typing import List, Optional, Union
from litestar import Controller, get, post, put, delete, Request
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import Parameter
from litestar.datastructures import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db_session
from app.models import Report, ReportExecution
from app.schemas import (
    ReportCreate, 
    ReportUpdate, 
    ReportResponse, 
    ReportWithExecutions,
    ExecutionTriggerRequest
)
from app.scheduler import scheduler
from app.worker import task_worker
from app.services.notebook_executor import NotebookExecutor

logger = logging.getLogger(__name__)


class ReportsController(Controller):
    """Controller for report management."""
    
    path = "/api/reports"
    
    def __init__(self, owner=None):
        super().__init__(owner)
    
    @get("/")
    async def get_reports(
        self,
        request: Request,
        db_session: AsyncSession,
        limit: int = Parameter(default=50, ge=1, le=100),
        offset: int = Parameter(default=0, ge=0),
        include_executions: bool = Parameter(default=False)
    ) -> List[Union[ReportResponse, ReportWithExecutions]]:
        """Get list of reports."""
        query = select(Report).where(~Report.name.startswith("temp_")).order_by(desc(Report.created_at)).offset(offset).limit(limit)
        
        if include_executions:
            query = query.options(
                # Load executions relationship
                select(Report).options(
                    select(ReportExecution).where(ReportExecution.report_id == Report.id)
                    .order_by(desc(ReportExecution.started_at))
                )
            )
        
        result = await db_session.execute(query)
        reports = result.scalars().all()
        
        if include_executions:
            return [ReportWithExecutions.model_validate(report) for report in reports]
        else:
            return [ReportResponse.model_validate(report) for report in reports]
    
    @get("/{report_id:int}")
    async def get_report(
        self,
        report_id: int,
        db_session: AsyncSession,
        include_executions: bool = Parameter(default=True)
    ) -> Union[ReportResponse, ReportWithExecutions]:
        """Get a specific report."""
        query = select(Report).where(Report.id == report_id)
        
        if include_executions:
            query = query.options(
                select(ReportExecution).where(ReportExecution.report_id == report_id)
                .order_by(desc(ReportExecution.started_at))
            )
        
        result = await db_session.execute(query)
        report = result.scalar_one_or_none()
        
        if not report:
            raise NotFoundException(f"Report with id {report_id} not found")
        
        if include_executions:
            return ReportWithExecutions.model_validate(report)
        else:
            return ReportResponse.model_validate(report)
    
    @post("/")
    async def create_report(
        self,
        data: ReportCreate,
        db_session: AsyncSession
    ) -> ReportResponse:
        """Create a new report."""
        report = Report(**data.model_dump())
        db_session.add(report)
        await db_session.commit()
        await db_session.refresh(report)
        
        return ReportResponse.model_validate(report)
    
    @put("/{report_id:int}")
    async def update_report(
        self,
        report_id: int,
        data: ReportUpdate,
        db_session: AsyncSession
    ) -> ReportResponse:
        """Update a report."""
        result = await db_session.execute(
            select(Report).where(Report.id == report_id)
        )
        report = result.scalar_one_or_none()
        
        if not report:
            raise NotFoundException(f"Report with id {report_id} not found")
        
        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(report, field, value)
        
        await db_session.commit()
        await db_session.refresh(report)
        
        return ReportResponse.model_validate(report)
    
    @delete("/{report_id:int}", status_code=200)
    async def delete_report(
        self,
        report_id: int,
        db_session: AsyncSession
    ) -> dict:
        """Delete a report."""
        result = await db_session.execute(
            select(Report).where(Report.id == report_id)
        )
        report = result.scalar_one_or_none()
        
        if not report:
            raise NotFoundException(f"Report with id {report_id} not found")
        
        await db_session.delete(report)
        await db_session.commit()
        
        return {"message": "Report deleted successfully"}
    
    @post("/{report_id:int}/execute")
    async def execute_report(
        self,
        report_id: int,
        db_session: AsyncSession
    ) -> dict:
        """Manually trigger report execution by creating a task."""
        try:
            task_id = await scheduler.create_manual_task(report_id, priority=1)
            return {
                "message": "Report execution task created",
                "task_id": task_id
            }
        except ValueError as e:
            raise NotFoundException(str(e))
        except Exception as e:
            raise ValidationException(detail=f"Failed to create execution task: {str(e)}")
    
    @get("/{report_id:int}/executions")
    async def get_report_executions(
        self,
        report_id: int,
        db_session: AsyncSession,
        limit: int = Parameter(default=20, ge=1, le=100),
        offset: int = Parameter(default=0, ge=0)
    ) -> List[dict]:
        """Get executions for a specific report."""
        result = await db_session.execute(
            select(ReportExecution)
            .where(ReportExecution.report_id == report_id)
            .order_by(desc(ReportExecution.started_at))
            .offset(offset)
            .limit(limit)
        )
        executions = result.scalars().all()
        
        return [
            {
                "id": exec.id,
                "status": exec.status,
                "started_at": exec.started_at,
                "completed_at": exec.completed_at,
                "error_message": exec.error_message,
                "html_output_path": exec.html_output_path,
                "artifacts": exec.artifacts,
                "execution_log": exec.execution_log
            }
            for exec in executions
        ]
    
    @post("/execute-direct")
    async def execute_direct(
        self,
        data: dict,
        db_session: AsyncSession
    ) -> dict:
        """Create a task for direct notebook execution."""
        try:
            # Extract data from request
            name = data.get("name")
            notebook_path = data.get("notebook_path")
            variables = data.get("variables", {})
            artifacts_config = data.get("artifacts_config", {})
            
            # Log the request for debugging
            logger.info(f"Creating report execution task: name={name}, notebook_path={notebook_path}, artifacts_config={artifacts_config}")
            
            if not name or not notebook_path:
                raise ValidationException(detail="Name and notebook_path are required")
            
            # Check if report already exists
            result = await db_session.execute(
                select(Report).where(Report.name == name)
            )
            existing_report = result.scalar_one_or_none()
            
            if existing_report:
                # Use existing report
                report = existing_report
            else:
                # Create a new permanent report
                report = Report(
                    name=name,
                    description=f"Report for {name}",
                    notebook_path=notebook_path,
                    is_active=True,
                    variables=variables,
                    artifacts_config=artifacts_config
                )
                db_session.add(report)
                await db_session.commit()
                await db_session.refresh(report)
            
            # Create a high-priority manual task
            task_id = await scheduler.create_manual_task(report.id, priority=2)
            
            return {
                "message": "Report execution task created",
                "task_id": task_id,
                "report_id": report.id
            }
            
        except Exception as e:
            raise ValidationException(detail=f"Failed to create execution task: {str(e)}")
    
    @post("/{report_id:int}/execute-with-file")
    async def execute_report_with_file(
        self,
        report_id: int,
        request: Request,
        db_session: AsyncSession
    ) -> dict:
        """Execute report with uploaded file."""
        try:
            # Get the report
            result = await db_session.execute(
                select(Report).where(Report.id == report_id)
            )
            report = result.scalar_one_or_none()
            
            if not report:
                raise NotFoundException(f"Report with id {report_id} not found")
            
            # Get uploaded file and variables from form data
            form_data = await request.form()
            uploaded_file = form_data.get("uploaded_file")
            variables_json = form_data.get("variables", "{}")
            
            # Parse variables
            try:
                variables = json.loads(variables_json)
            except json.JSONDecodeError:
                variables = {}
            
            # Update report variables if provided
            if variables:
                report.variables = variables
                await db_session.commit()
            
            # Create task with file information
            task_id = await scheduler.create_manual_task_with_file(
                report_id, 
                priority=1,
                uploaded_file=uploaded_file
            )
            
            return {
                "message": "Report execution task created with file",
                "task_id": task_id
            }
            
        except Exception as e:
            logger.error(f"Error executing report with file: {e}")
            raise ValidationException(detail=f"Failed to create execution task: {str(e)}")
    
    @get("/{report_id:int}/variables")
    async def get_report_variables(
        self,
        report_id: int,
        db_session: AsyncSession
    ) -> dict:
        """Get environment variables for a specific report."""
        try:
            # Get the report
            result = await db_session.execute(
                select(Report).where(Report.id == report_id)
            )
            report = result.scalar_one_or_none()
            
            if not report:
                raise NotFoundException(f"Report with id {report_id} not found")
            
            # Scan notebook for variables
            executor = NotebookExecutor()
            variables = executor.scan_notebook_variables(report.notebook_path)
            
            return {
                "variables": variables,
                "notebook_path": report.notebook_path
            }
            
        except Exception as e:
            logger.error(f"Error getting report variables: {e}")
            raise ValidationException(detail=f"Failed to get report variables: {str(e)}")
    
    @delete("/cleanup-old", status_code=200)
    async def cleanup_old_reports(
        self,
        db_session: AsyncSession
    ) -> dict:
        """Clean up old reports without executions older than 7 days."""
        from datetime import timedelta
        
        # Delete reports without executions older than 7 days
        cutoff_time = datetime.now() - timedelta(days=7)
        
        result = await db_session.execute(
            select(Report)
            .where(Report.created_at < cutoff_time)
            .where(~Report.executions.any())  # No executions
        )
        old_reports = result.scalars().all()
        
        deleted_count = 0
        for report in old_reports:
            await db_session.delete(report)
            deleted_count += 1
        
        await db_session.commit()
        
        return {
            "message": f"Cleaned up {deleted_count} old reports without executions",
            "deleted_count": deleted_count
        }
