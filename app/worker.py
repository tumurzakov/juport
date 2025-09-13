"""Background task worker for processing report execution tasks."""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from app.database import async_session_factory
from app.models import Task, Report, ReportExecution, Schedule
from app.services.notebook_executor import NotebookExecutor

logger = logging.getLogger(__name__)


class TaskWorker:
    """Background worker for processing tasks from the queue."""
    
    def __init__(self):
        self.executor = NotebookExecutor()
        self.running = False
        self._task = None
    
    async def start(self):
        """Start the worker task."""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._worker_loop())
        logger.info("Task worker started")
    
    async def stop(self):
        """Stop the worker task."""
        if not self.running:
            return
        
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Task worker stopped")
    
    async def _worker_loop(self):
        """Main worker loop."""
        while self.running:
            try:
                await self._process_next_task()
                # Small delay to prevent busy waiting
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                await asyncio.sleep(5)  # Wait longer on error
    
    async def _process_next_task(self):
        """Process the next pending task."""
        async with async_session_factory() as session:
            # Get the next pending task (highest priority first, then oldest)
            result = await session.execute(
                select(Task)
                .where(Task.status == "pending")
                .order_by(Task.priority.desc(), Task.created_at.asc())
                .limit(1)
                .options(
                    selectinload(Task.report),
                    selectinload(Task.schedule)
                )
            )
            task = result.scalar_one_or_none()
            
            if not task:
                return  # No pending tasks
            
            await self._execute_task(task, session)
    
    async def _execute_task(self, task: Task, session: AsyncSession):
        """Execute a single task."""
        logger.info(f"Starting task {task.id} for report {task.report.name}")
        
        # Update task status to running
        task.status = "running"
        task.started_at = datetime.now()
        await session.commit()
        
        try:
            # Create report execution record
            report_execution = ReportExecution(
                report_id=task.report_id,
                status="running",
                started_at=datetime.now()
            )
            session.add(report_execution)
            await session.commit()
            await session.refresh(report_execution)
            
            # Link task to report execution
            task.report_execution_id = report_execution.id
            await session.commit()
            
            # Execute the notebook
            logger.info(f"Executing notebook with artifacts_config: {task.report.artifacts_config}")
            result = await self.executor.execute_notebook(
                task.report.notebook_path,
                task.report.variables or {},
                task.report.artifacts_config or {},
                task_id=task.id
            )
            logger.info(f"Notebook execution result: artifacts={len(result.get('artifacts', []))}, html_path={result.get('html_path')}")
            
            # Update report execution with results
            report_execution.status = "completed"
            report_execution.completed_at = datetime.now()
            report_execution.html_output_path = result.get("html_path")
            report_execution.artifacts = result.get("artifacts", [])
            report_execution.execution_log = result.get("log", "")
            
            # Update task status
            task.status = "completed"
            task.completed_at = datetime.now()
            task.execution_log = "Task completed successfully"
            
            # Update schedule if this was a scheduled task
            if task.schedule_id and task.schedule:
                task.schedule.last_run = datetime.now()
                from croniter import croniter
                cron = croniter(task.schedule.cron_expression, datetime.now())
                task.schedule.next_run = cron.get_next(datetime)
            
            await session.commit()
            logger.info(f"Task {task.id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error executing task {task.id}: {e}")
            
            # Update task with error
            task.status = "failed"
            task.completed_at = datetime.now()
            task.error_message = str(e)
            
            # Update report execution with error if it exists
            if task.report_execution_id:
                result = await session.execute(
                    select(ReportExecution).where(ReportExecution.id == task.report_execution_id)
                )
                report_execution = result.scalar_one_or_none()
                if report_execution:
                    report_execution.status = "failed"
                    report_execution.completed_at = datetime.now()
                    report_execution.error_message = str(e)
            
            await session.commit()
    
    async def get_task_status(self, task_id: int) -> Optional[Task]:
        """Get task status by ID."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Task).where(Task.id == task_id)
            )
            return result.scalar_one_or_none()
    
    async def get_queue_status(self) -> dict:
        """Get current queue status."""
        async with async_session_factory() as session:
            # Count tasks by status
            pending_result = await session.execute(
                select(Task).where(Task.status == "pending")
            )
            pending_count = len(pending_result.scalars().all())
            
            running_result = await session.execute(
                select(Task).where(Task.status == "running")
            )
            running_count = len(running_result.scalars().all())
            
            return {
                "pending": pending_count,
                "running": running_count,
                "worker_running": self.running
            }


# Global worker instance
task_worker = TaskWorker()
