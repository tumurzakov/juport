"""Pydantic schemas for API requests and responses."""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ReportBase(BaseModel):
    """Base report schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    notebook_path: str = Field(..., min_length=1, max_length=500)
    schedule_cron: str = Field(..., min_length=1, max_length=100)
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
    schedule_cron: Optional[str] = Field(None, min_length=1, max_length=100)
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
