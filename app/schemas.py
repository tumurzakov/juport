"""Pydantic schemas for API requests and responses."""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ReportBase(BaseModel):
    """Base report schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    notebook_path: str = Field(..., min_length=1, max_length=500)
    is_active: bool = True
    artifacts_config: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None


class ReportCreate(ReportBase):
    """Schema for creating a new report."""
    pass


class ReportUpdate(BaseModel):
    """Schema for updating a report."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    notebook_path: Optional[str] = Field(None, min_length=1, max_length=500)
    is_active: Optional[bool] = None
    artifacts_config: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None


class ReportResponse(ReportBase):
    """Schema for report response."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class ReportExecutionResponse(BaseModel):
    """Schema for report execution response."""
    id: int
    report_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    html_output_path: Optional[str] = None
    artifacts: Optional[List[Dict[str, str]]] = None
    execution_log: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class ReportWithExecutions(ReportResponse):
    """Schema for report with executions."""
    executions: List[ReportExecutionResponse] = []


class NotebookInfo(BaseModel):
    """Schema for notebook information."""
    name: str
    path: str
    size: int
    modified: datetime


class ExecutionTriggerRequest(BaseModel):
    """Schema for manually triggering report execution."""
    report_id: int


# Schedule schemas
class ScheduleBase(BaseModel):
    """Base schedule schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    report_id: int = Field(..., gt=0)
    cron_expression: str = Field(..., min_length=1, max_length=100)
    is_active: bool = True
    timezone: str = Field(default="UTC", max_length=50)


class ScheduleCreate(ScheduleBase):
    """Schema for creating a new schedule."""
    pass


class ScheduleUpdate(BaseModel):
    """Schema for updating a schedule."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    cron_expression: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    timezone: Optional[str] = Field(None, max_length=50)


class ScheduleResponse(ScheduleBase):
    """Schema for schedule response."""
    id: int
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class ScheduleExecutionResponse(BaseModel):
    """Schema for schedule execution response."""
    id: int
    schedule_id: int
    report_execution_id: Optional[int] = None
    status: str
    scheduled_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    execution_log: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class ScheduleWithExecutions(ScheduleResponse):
    """Schema for schedule with executions."""
    executions: List[ScheduleExecutionResponse] = []
    report: Optional[ReportResponse] = None


class ScheduleTriggerRequest(BaseModel):
    """Schema for manually triggering schedule execution."""
    schedule_id: int


# Task schemas
class TaskBase(BaseModel):
    """Base task schema."""
    report_id: int = Field(..., gt=0)
    schedule_id: Optional[int] = Field(None, gt=0)
    task_type: str = Field(..., pattern="^(manual|scheduled)$")
    priority: int = Field(default=0)


class TaskCreate(TaskBase):
    """Schema for creating a new task."""
    pass


class TaskResponse(BaseModel):
    """Schema for task response."""
    id: int
    report_id: int
    schedule_id: Optional[int] = None
    task_type: str
    status: str
    priority: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    execution_log: Optional[str] = None
    report_execution_id: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class TaskWithDetails(TaskResponse):
    """Schema for task with related data."""
    report: Optional[ReportResponse] = None
    schedule: Optional[ScheduleResponse] = None
