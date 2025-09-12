"""Database models."""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Report(Base):
    """Report configuration model."""
    __tablename__ = "reports"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    notebook_path = Column(String(500), nullable=False)
    schedule_cron = Column(String(100), nullable=False, default="")  # Cron expression for scheduling
    is_active = Column(Boolean, default=True)
    artifacts_config = Column(JSON)  # Configuration for output artifacts
    variables = Column(JSON)  # Variables to pass to notebook
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    executions = relationship("ReportExecution", back_populates="report", cascade="all, delete-orphan")


class ReportExecution(Base):
    """Report execution result model."""
    __tablename__ = "report_executions"
    
    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False)
    status = Column(String(50), nullable=False)  # pending, running, completed, failed
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    html_output_path = Column(String(500))
    artifacts = Column(JSON)  # List of generated artifacts with paths
    execution_log = Column(Text)
    
    # Relationships
    report = relationship("Report", back_populates="executions")


class Schedule(Base):
    """Schedule configuration model for managing report schedules."""
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False)
    cron_expression = Column(String(100), nullable=False)  # Cron expression
    is_active = Column(Boolean, default=True)
    timezone = Column(String(50), default="UTC")  # Timezone for schedule
    last_run = Column(DateTime(timezone=True))  # Last execution time
    next_run = Column(DateTime(timezone=True))  # Next scheduled execution
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    report = relationship("Report", backref="schedules")
    executions = relationship("ScheduleExecution", back_populates="schedule", cascade="all, delete-orphan")


class ScheduleExecution(Base):
    """Schedule execution result model."""
    __tablename__ = "schedule_executions"
    
    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=False)
    report_execution_id = Column(Integer, ForeignKey("report_executions.id"), nullable=True)
    status = Column(String(50), nullable=False)  # pending, running, completed, failed, skipped
    scheduled_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    execution_log = Column(Text)
    
    # Relationships
    schedule = relationship("Schedule", back_populates="executions")
    report_execution = relationship("ReportExecution", backref="schedule_executions")


class Task(Base):
    """Task queue model for background report execution."""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=True)  # Null for manual tasks
    task_type = Column(String(50), nullable=False)  # manual, scheduled
    status = Column(String(50), nullable=False, default="pending")  # pending, running, completed, failed
    priority = Column(Integer, default=0)  # Higher number = higher priority
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    execution_log = Column(Text)
    report_execution_id = Column(Integer, ForeignKey("report_executions.id"), nullable=True)
    
    # Relationships
    report = relationship("Report", backref="tasks")
    schedule = relationship("Schedule", backref="tasks")
    report_execution = relationship("ReportExecution", backref="tasks")
