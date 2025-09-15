"""Task scheduler for running reports."""
import asyncio
import logging
import threading
from datetime import datetime
from typing import List
from croniter import croniter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from app.database import async_session_factory
from app.models import Report, ReportExecution, Schedule, ScheduleExecution, Task

logger = logging.getLogger(__name__)


class Scheduler:
    """Scheduler for creating tasks based on cron expressions."""
    
    def __init__(self):
        self.running = False
        self._task = None
    
    async def start(self):
        """Start the scheduler."""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler started")
    
    async def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                await self._check_and_run_reports()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(60)
    
    async def _check_and_run_reports(self):
        """Check which schedules should be run and execute them."""
        async with async_session_factory() as session:
            # Get all active schedules that are due to run
            now = datetime.now()
            result = await session.execute(
                select(Schedule)
                .where(
                    and_(
                        Schedule.is_active == True,
                        Schedule.next_run <= now
                    )
                )
                .options(selectinload(Schedule.report))
            )
            schedules = result.scalars().all()
            
            for schedule in schedules:
                try:
                    if self._should_run_schedule(schedule):
                        await self._run_schedule(schedule, session)
                except Exception as e:
                    logger.error(f"Error checking schedule {schedule.name}: {e}")
    
    def _should_run_schedule(self, schedule: Schedule) -> bool:
        """Check if schedule should be run based on next_run time."""
        try:
            # Check if the schedule is due to run (within the last minute)
            if schedule.next_run is None:
                return False
            
            time_diff = datetime.now() - schedule.next_run
            return time_diff.total_seconds() >= 0 and time_diff.total_seconds() < 60
            
        except Exception as e:
            logger.error(f"Error checking schedule {schedule.name}: {e}")
            return False
    
    async def _run_schedule(self, schedule: Schedule, session: AsyncSession):
        """Create a task for a specific schedule."""
        logger.info(f"Creating task for schedule: {schedule.name}")
        
        try:
            # Create a task for this schedule
            task = Task(
                report_id=schedule.report_id,
                schedule_id=schedule.id,
                task_type="scheduled",
                priority=0,  # Normal priority for scheduled tasks
                status="pending"
            )
            session.add(task)
            await session.commit()
            
            # Update schedule last_run and next_run
            schedule.last_run = datetime.now()
            cron = croniter(schedule.cron_expression, datetime.now())
            schedule.next_run = cron.get_next(datetime)
            
            await session.commit()
            logger.info(f"Task created for schedule {schedule.name} (task_id: {task.id})")
            
        except Exception as e:
            logger.error(f"Error creating task for schedule {schedule.name}: {e}")
            await session.rollback()
    
    async def _run_report(self, report: Report, session: AsyncSession):
        """Run a specific report (legacy method for backward compatibility)."""
        logger.info(f"Starting execution of report: {report.name}")
        
        # Create execution time once and use it for both DB and folder
        execution_time = datetime.now()
        
        # Create execution record
        execution = ReportExecution(
            report_id=report.id,
            status="running",
            started_at=execution_time
        )
        session.add(execution)
        await session.commit()
        
        try:
            # Execute the notebook
            # Format execution_time to match execution directory format
            execution_datetime = execution_time.strftime("%Y-%m-%d_%H-%M-%S")
            result = await self.executor.execute_notebook(
                report.notebook_path,
                report.variables or {},
                report.artifacts_config or {},
                execution_datetime=execution_datetime
            )
            
            # Update execution record with results
            execution.status = "completed"
            execution.completed_at = datetime.now()
            execution.html_output_path = result.get("html_path")
            execution.artifacts = result.get("artifacts", [])
            execution.execution_log = result.get("log", "")
            
            await session.commit()
            logger.info(f"Report {report.name} completed successfully")
            
        except Exception as e:
            logger.error(f"Error executing report {report.name}: {e}")
            
            # Update execution record with error
            execution.status = "failed"
            execution.completed_at = datetime.now()
            execution.error_message = str(e)
            
            await session.commit()
    
    async def create_manual_task(self, report_id: int, priority: int = 1) -> int:
        """Create a manual task for report execution."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Report).where(Report.id == report_id)
            )
            report = result.scalar_one_or_none()
            
            if not report:
                raise ValueError(f"Report with id {report_id} not found")
            
            # Create a manual task
            task = Task(
                report_id=report_id,
                schedule_id=None,
                task_type="manual",
                priority=priority,  # Higher priority for manual tasks
                status="pending"
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            
            logger.info(f"Manual task created for report {report.name} (task_id: {task.id})")
            return task.id
    
    async def create_manual_task_with_file(self, report_id: int, priority: int = 1, uploaded_file=None) -> int:
        """Create a manual task for report execution with uploaded file."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Report).where(Report.id == report_id)
            )
            report = result.scalar_one_or_none()
            
            if not report:
                raise ValueError(f"Report with id {report_id} not found")
            
            # Create a manual task
            task = Task(
                report_id=report_id,
                schedule_id=None,
                task_type="manual",
                priority=priority,  # Higher priority for manual tasks
                status="pending"
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            
            # Store uploaded file if provided
            if uploaded_file:
                await self._store_uploaded_file(task.id, uploaded_file)
            
            logger.info(f"Manual task created for report {report.name} with file (task_id: {task.id})")
            return task.id
    
    async def create_manual_task_with_files(self, report_id: int, priority: int = 1, uploaded_files=None) -> int:
        """Create a manual task for report execution with uploaded files."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Report).where(Report.id == report_id)
            )
            report = result.scalar_one_or_none()
            
            if not report:
                raise ValueError(f"Report with id {report_id} not found")
            
            # Create a manual task
            task = Task(
                report_id=report_id,
                schedule_id=None,
                task_type="manual",
                priority=priority,  # Higher priority for manual tasks
                status="pending"
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            
            # Store uploaded files if provided
            if uploaded_files:
                await self._store_uploaded_files(task.id, uploaded_files)
            
            logger.info(f"Manual task created for report {report.name} with {len(uploaded_files) if uploaded_files else 0} files (task_id: {task.id})")
            return task.id
    
    async def _store_uploaded_file(self, task_id: int, uploaded_file):
        """Store uploaded file for task execution."""
        import os
        import shutil
        from pathlib import Path
        
        try:
            # Create directory for uploaded files
            uploads_dir = Path("data/uploads")
            uploads_dir.mkdir(parents=True, exist_ok=True)
            
            # Save file with task_id prefix
            filename = f"task_{task_id}_{uploaded_file.filename}"
            file_path = uploads_dir / filename
            
            # Write file content
            with open(file_path, "wb") as f:
                content = await uploaded_file.read()
                f.write(content)
            
            logger.info(f"Uploaded file saved: {file_path}")
            
        except Exception as e:
            logger.error(f"Error storing uploaded file: {e}")
            raise
    
    async def _store_uploaded_files(self, task_id: int, uploaded_files):
        """Store multiple uploaded files for task execution."""
        import os
        import shutil
        from pathlib import Path
        
        try:
            # Create directory for uploaded files
            uploads_dir = Path("data/uploads")
            uploads_dir.mkdir(parents=True, exist_ok=True)
            
            stored_files = []
            for i, uploaded_file in enumerate(uploaded_files):
                if uploaded_file and uploaded_file.filename:
                    # Save file with task_id prefix and index
                    filename = f"task_{task_id}_{i}_{uploaded_file.filename}"
                    file_path = uploads_dir / filename
                    
                    # Write file content
                    with open(file_path, "wb") as f:
                        content = await uploaded_file.read()
                        f.write(content)
                    
                    stored_files.append(file_path)
                    logger.info(f"Uploaded file {i+1} saved: {file_path}")
            
            logger.info(f"Stored {len(stored_files)} files for task {task_id}")
            
        except Exception as e:
            logger.error(f"Error storing uploaded files: {e}")
            raise


# Global scheduler instance
scheduler = Scheduler()
