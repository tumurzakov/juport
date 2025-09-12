"""Task scheduler for running reports."""
import asyncio
import logging
from datetime import datetime
from typing import List
from croniter import croniter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import async_session_factory
from app.models import Report, ReportExecution
from app.services.notebook_executor import NotebookExecutor

logger = logging.getLogger(__name__)


class Scheduler:
    """Scheduler for running reports based on cron expressions."""
    
    def __init__(self):
        self.executor = NotebookExecutor()
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
        """Check which reports should be run and execute them."""
        async with async_session_factory() as session:
            # Get all active reports
            result = await session.execute(
                select(Report).where(Report.is_active == True)
            )
            reports = result.scalars().all()
            
            for report in reports:
                try:
                    if self._should_run_report(report):
                        await self._run_report(report, session)
                except Exception as e:
                    logger.error(f"Error checking report {report.name}: {e}")
    
    def _should_run_report(self, report: Report) -> bool:
        """Check if report should be run based on cron expression."""
        try:
            # Get the last execution time
            # For simplicity, we'll check if it's time to run based on current time
            # In a real implementation, you'd want to track last execution time
            cron = croniter(report.schedule_cron, datetime.now())
            next_run = cron.get_next(datetime)
            prev_run = cron.get_prev(datetime)
            
            # If the previous run time is within the last minute, it's time to run
            time_diff = datetime.now() - prev_run
            return time_diff.total_seconds() < 60
            
        except Exception as e:
            logger.error(f"Error parsing cron expression for report {report.name}: {e}")
            return False
    
    async def _run_report(self, report: Report, session: AsyncSession):
        """Run a specific report."""
        logger.info(f"Starting execution of report: {report.name}")
        
        # Create execution record
        execution = ReportExecution(
            report_id=report.id,
            status="running",
            started_at=datetime.now()
        )
        session.add(execution)
        await session.commit()
        
        try:
            # Execute the notebook
            result = await self.executor.execute_notebook(
                report.notebook_path,
                report.variables or {},
                report.artifacts_config or {}
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
    
    async def run_report_manually(self, report_id: int) -> int:
        """Manually trigger a report execution."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Report).where(Report.id == report_id)
            )
            report = result.scalar_one_or_none()
            
            if not report:
                raise ValueError(f"Report with id {report_id} not found")
            
            await self._run_report(report, session)
            
            # Return the execution id
            result = await session.execute(
                select(ReportExecution)
                .where(ReportExecution.report_id == report_id)
                .order_by(ReportExecution.started_at.desc())
                .limit(1)
            )
            execution = result.scalar_one()
            return execution.id


# Global scheduler instance
scheduler = Scheduler()
