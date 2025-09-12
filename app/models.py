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
    schedule_cron = Column(String(100), nullable=False)  # Cron expression
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
