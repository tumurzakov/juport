"""Schedule management API routes."""
from datetime import datetime
from typing import List, Optional, Union
from litestar import Controller, get, post, put, delete, Request
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import Parameter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from sqlalchemy.orm import selectinload
from croniter import croniter
from app.database import get_db_session
from app.models import Schedule, ScheduleExecution, Report, ReportExecution
from app.schemas import (
    ScheduleCreate, 
    ScheduleUpdate, 
    ScheduleResponse, 
    ScheduleWithExecutions,
    ScheduleExecutionResponse,
    ScheduleTriggerRequest
)
from app.scheduler import scheduler
from app.worker import task_worker


class SchedulesController(Controller):
    """Controller for schedule management."""
    
    path = "/api/schedules"
    
    def __init__(self, owner=None):
        super().__init__(owner)
    
    @get("/")
    async def get_schedules(
        self,
        request: Request,
        db_session: AsyncSession,
        limit: int = Parameter(default=50, ge=1, le=100),
        offset: int = Parameter(default=0, ge=0),
        include_executions: bool = Parameter(default=False),
        report_id: Optional[int] = Parameter(default=None)
    ) -> List[Union[ScheduleResponse, ScheduleWithExecutions]]:
        """Get list of schedules."""
        query = select(Schedule).order_by(desc(Schedule.created_at))
        
        if report_id:
            query = query.where(Schedule.report_id == report_id)
        
        query = query.offset(offset).limit(limit)
        
        if include_executions:
            query = query.options(
                selectinload(Schedule.executions),
                selectinload(Schedule.report)
            )
        
        result = await db_session.execute(query)
        schedules = result.scalars().all()
        
        if include_executions:
            return [ScheduleWithExecutions.model_validate(schedule) for schedule in schedules]
        else:
            return [ScheduleResponse.model_validate(schedule) for schedule in schedules]
    
    @get("/{schedule_id:int}")
    async def get_schedule(
        self,
        schedule_id: int,
        db_session: AsyncSession,
        include_executions: bool = Parameter(default=True)
    ) -> Union[ScheduleResponse, ScheduleWithExecutions]:
        """Get a specific schedule."""
        query = select(Schedule).where(Schedule.id == schedule_id)
        
        if include_executions:
            query = query.options(
                selectinload(Schedule.executions),
                selectinload(Schedule.report)
            )
        
        result = await db_session.execute(query)
        schedule = result.scalar_one_or_none()
        
        if not schedule:
            raise NotFoundException(f"Schedule with id {schedule_id} not found")
        
        if include_executions:
            return ScheduleWithExecutions.model_validate(schedule)
        else:
            return ScheduleResponse.model_validate(schedule)
    
    @post("/")
    async def create_schedule(
        self,
        data: ScheduleCreate,
        db_session: AsyncSession
    ) -> ScheduleResponse:
        """Create a new schedule."""
        # Validate that the report exists
        result = await db_session.execute(
            select(Report).where(Report.id == data.report_id)
        )
        report = result.scalar_one_or_none()
        
        if not report:
            raise ValidationException(detail=f"Report with id {data.report_id} not found")
        
        # Validate cron expression
        try:
            croniter(data.cron_expression, datetime.now())
        except Exception as e:
            raise ValidationException(detail=f"Invalid cron expression: {str(e)}")
        
        # Calculate next run time
        cron = croniter(data.cron_expression, datetime.now())
        next_run = cron.get_next(datetime)
        
        schedule = Schedule(
            **data.model_dump(),
            next_run=next_run
        )
        db_session.add(schedule)
        await db_session.commit()
        await db_session.refresh(schedule)
        
        return ScheduleResponse.model_validate(schedule)
    
    @put("/{schedule_id:int}")
    async def update_schedule(
        self,
        schedule_id: int,
        data: ScheduleUpdate,
        db_session: AsyncSession
    ) -> ScheduleResponse:
        """Update a schedule."""
        result = await db_session.execute(
            select(Schedule).where(Schedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        
        if not schedule:
            raise NotFoundException(f"Schedule with id {schedule_id} not found")
        
        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(schedule, field, value)
        
        # Recalculate next run time if cron expression changed
        if 'cron_expression' in update_data:
            try:
                cron = croniter(schedule.cron_expression, datetime.now())
                schedule.next_run = cron.get_next(datetime)
            except Exception as e:
                raise ValidationException(detail=f"Invalid cron expression: {str(e)}")
        
        await db_session.commit()
        await db_session.refresh(schedule)
        
        return ScheduleResponse.model_validate(schedule)
    
    @delete("/{schedule_id:int}", status_code=200)
    async def delete_schedule(
        self,
        schedule_id: int,
        db_session: AsyncSession
    ) -> dict:
        """Delete a schedule."""
        result = await db_session.execute(
            select(Schedule).where(Schedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        
        if not schedule:
            raise NotFoundException(f"Schedule with id {schedule_id} not found")
        
        await db_session.delete(schedule)
        await db_session.commit()
        
        return {"message": "Schedule deleted successfully"}
    
    @post("/{schedule_id:int}/execute")
    async def execute_schedule(
        self,
        schedule_id: int,
        db_session: AsyncSession
    ) -> dict:
        """Manually trigger schedule execution by creating a task."""
        result = await db_session.execute(
            select(Schedule).where(Schedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        
        if not schedule:
            raise NotFoundException(f"Schedule with id {schedule_id} not found")
        
        if not schedule.is_active:
            raise ValidationException(detail="Cannot execute inactive schedule")
        
        try:
            # Create a high-priority manual task for this schedule
            task_id = await scheduler.create_manual_task(schedule.report_id, priority=1)
            
            return {
                "message": "Schedule execution task created",
                "task_id": task_id,
                "schedule_id": schedule_id
            }
            
        except Exception as e:
            raise ValidationException(detail=f"Failed to create schedule execution task: {str(e)}")
    
    @get("/{schedule_id:int}/executions")
    async def get_schedule_executions(
        self,
        schedule_id: int,
        db_session: AsyncSession,
        limit: int = Parameter(default=20, ge=1, le=100),
        offset: int = Parameter(default=0, ge=0)
    ) -> List[ScheduleExecutionResponse]:
        """Get executions for a specific schedule."""
        result = await db_session.execute(
            select(ScheduleExecution)
            .where(ScheduleExecution.schedule_id == schedule_id)
            .order_by(desc(ScheduleExecution.scheduled_at))
            .offset(offset)
            .limit(limit)
        )
        executions = result.scalars().all()
        
        return [ScheduleExecutionResponse.model_validate(exec) for exec in executions]
    
    @get("/active")
    async def get_active_schedules(
        self,
        db_session: AsyncSession
    ) -> List[ScheduleResponse]:
        """Get all active schedules."""
        result = await db_session.execute(
            select(Schedule)
            .where(Schedule.is_active == True)
            .order_by(Schedule.next_run.asc())
        )
        schedules = result.scalars().all()
        
        return [ScheduleResponse.model_validate(schedule) for schedule in schedules]
    
    @post("/validate-cron")
    async def validate_cron_expression(
        self,
        data: dict
    ) -> dict:
        """Validate a cron expression."""
        cron_expression = data.get("cron_expression")
        
        if not cron_expression:
            raise ValidationException(detail="cron_expression is required")
        
        try:
            cron = croniter(cron_expression, datetime.now())
            next_run = cron.get_next(datetime)
            prev_run = cron.get_prev(datetime)
            
            return {
                "valid": True,
                "next_run": next_run.isoformat(),
                "previous_run": prev_run.isoformat(),
                "description": f"Next execution: {next_run.strftime('%Y-%m-%d %H:%M:%S')}"
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }
    
    @put("/{schedule_id:int}/toggle")
    async def toggle_schedule(
        self,
        schedule_id: int,
        db_session: AsyncSession
    ) -> ScheduleResponse:
        """Toggle schedule active status."""
        result = await db_session.execute(
            select(Schedule).where(Schedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        
        if not schedule:
            raise NotFoundException(f"Schedule with id {schedule_id} not found")
        
        schedule.is_active = not schedule.is_active
        
        # Recalculate next run time if activating
        if schedule.is_active:
            cron = croniter(schedule.cron_expression, datetime.now())
            schedule.next_run = cron.get_next(datetime)
        else:
            schedule.next_run = None
        
        await db_session.commit()
        await db_session.refresh(schedule)
        
        return ScheduleResponse.model_validate(schedule)
