"""Task management API routes."""
from datetime import datetime
from typing import List, Optional, Union
from litestar import Controller, get, post, delete, Request
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import Parameter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from sqlalchemy.orm import selectinload
from app.database import get_db_session
from app.models import Task, Report, Schedule
from app.schemas import (
    TaskResponse, 
    TaskWithDetails
)
from app.worker import task_worker


class TasksController(Controller):
    """Controller for task management."""
    
    path = "/api/tasks"
    
    def __init__(self, owner=None):
        super().__init__(owner)
    
    @get("/")
    async def get_tasks(
        self,
        request: Request,
        db_session: AsyncSession,
        limit: int = Parameter(default=50, ge=1, le=100),
        offset: int = Parameter(default=0, ge=0),
        status: Optional[str] = Parameter(default=None),
        task_type: Optional[str] = Parameter(default=None),
        report_id: Optional[int] = Parameter(default=None)
    ) -> List[Union[TaskResponse, TaskWithDetails]]:
        """Get list of tasks."""
        query = select(Task).order_by(desc(Task.created_at))
        
        if status:
            query = query.where(Task.status == status)
        
        if task_type:
            query = query.where(Task.task_type == task_type)
        
        if report_id:
            query = query.where(Task.report_id == report_id)
        
        query = query.offset(offset).limit(limit)
        
        # Always include related data
        query = query.options(
            selectinload(Task.report),
            selectinload(Task.schedule)
        )
        
        result = await db_session.execute(query)
        tasks = result.scalars().all()
        
        return [TaskWithDetails.model_validate(task) for task in tasks]
    
    @get("/{task_id:int}")
    async def get_task(
        self,
        task_id: int,
        db_session: AsyncSession
    ) -> TaskWithDetails:
        """Get a specific task."""
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
            raise NotFoundException(f"Task with id {task_id} not found")
        
        return TaskWithDetails.model_validate(task)
    
    @get("/queue/status")
    async def get_queue_status(
        self,
        db_session: AsyncSession
    ) -> dict:
        """Get current task queue status."""
        # Get counts by status
        pending_result = await db_session.execute(
            select(Task).where(Task.status == "pending")
        )
        pending_count = len(pending_result.scalars().all())
        
        running_result = await db_session.execute(
            select(Task).where(Task.status == "running")
        )
        running_count = len(running_result.scalars().all())
        
        completed_result = await db_session.execute(
            select(Task).where(Task.status == "completed")
        )
        completed_count = len(completed_result.scalars().all())
        
        failed_result = await db_session.execute(
            select(Task).where(Task.status == "failed")
        )
        failed_count = len(failed_result.scalars().all())
        
        return {
            "pending": pending_count,
            "running": running_count,
            "completed": completed_count,
            "failed": failed_count,
            "worker_running": task_worker.running
        }
    
    @get("/pending")
    async def get_pending_tasks(
        self,
        db_session: AsyncSession,
        limit: int = Parameter(default=10, ge=1, le=50)
    ) -> List[TaskResponse]:
        """Get pending tasks (for monitoring)."""
        result = await db_session.execute(
            select(Task)
            .where(Task.status == "pending")
            .order_by(Task.priority.desc(), Task.created_at.asc())
            .limit(limit)
        )
        tasks = result.scalars().all()
        
        return [TaskResponse.model_validate(task) for task in tasks]
    
    @get("/running")
    async def get_running_tasks(
        self,
        db_session: AsyncSession
    ) -> List[TaskWithDetails]:
        """Get currently running tasks."""
        result = await db_session.execute(
            select(Task)
            .where(Task.status == "running")
            .order_by(Task.started_at.asc())
            .options(
                selectinload(Task.report),
                selectinload(Task.schedule)
            )
        )
        tasks = result.scalars().all()
        
        return [TaskWithDetails.model_validate(task) for task in tasks]
    
    @delete("/{task_id:int}", status_code=200)
    async def cancel_task(
        self,
        task_id: int,
        db_session: AsyncSession
    ) -> dict:
        """Cancel a pending task."""
        result = await db_session.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            raise NotFoundException(f"Task with id {task_id} not found")
        
        if task.status not in ["pending"]:
            raise ValidationException(detail="Can only cancel pending tasks")
        
        task.status = "failed"
        task.completed_at = datetime.now()
        task.error_message = "Task cancelled by user"
        
        await db_session.commit()
        
        return {"message": "Task cancelled successfully"}
    
    @delete("/cleanup-completed", status_code=200)
    async def cleanup_completed_tasks(
        self,
        db_session: AsyncSession,
        older_than_hours: int = Parameter(default=24, ge=1, le=168)
    ) -> dict:
        """Clean up old completed and failed tasks."""
        from datetime import timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
        
        result = await db_session.execute(
            select(Task)
            .where(
                and_(
                    Task.status.in_(["completed", "failed"]),
                    Task.completed_at < cutoff_time
                )
            )
        )
        old_tasks = result.scalars().all()
        
        deleted_count = 0
        for task in old_tasks:
            await db_session.delete(task)
            deleted_count += 1
        
        await db_session.commit()
        
        return {
            "message": f"Cleaned up {deleted_count} old tasks",
            "deleted_count": deleted_count
        }
