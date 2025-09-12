#!/usr/bin/env python3
"""Initialize database with sample data."""
import asyncio
import sys
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).parent.parent))

from app.database import async_session_factory, engine
from app.models import Base, Report
from app.config import settings


async def init_database():
    """Initialize database with tables and sample data."""
    print("Creating database tables...")
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("Database tables created successfully!")
    
    # Add sample reports
    async with async_session_factory() as session:
        # Check if reports already exist
        existing_reports = await session.execute("SELECT COUNT(*) FROM reports")
        count = existing_reports.scalar()
        
        if count > 0:
            print(f"Database already contains {count} reports. Skipping sample data.")
            return
        
        print("Adding sample reports...")
        
        # Sample report 1: Debtors report
        debtors_report = Report(
            name="Отчет по должникам",
            description="Ежемесячный отчет по должникам с анализом задолженности",
            notebook_path="debtors.ipynb",
            schedule_cron="0 9 1 * *",  # 1st day of month at 9:00 AM
            is_active=True,
            artifacts_config={
                "files": [
                    {
                        "name": "debtors_report_{execution_id}.xlsx",
                        "type": "excel",
                        "description": "Основной отчет по должникам"
                    },
                    {
                        "name": "debtors_analytics_{execution_id}.xlsx", 
                        "type": "excel",
                        "description": "Аналитический отчет с прогнозами"
                    },
                    {
                        "name": "debtors_analysis.png",
                        "type": "image",
                        "description": "Графики анализа долгов"
                    }
                ]
            },
            variables={
                "min_debt_amount": 1000,
                "days_overdue": 30,
                "report_date": "auto"
            }
        )
        
        # Sample report 2: Sales report
        sales_report = Report(
            name="Отчет по продажам",
            description="Еженедельный отчет по продажам и выручке",
            notebook_path="sales.ipynb",
            schedule_cron="0 8 * * 1",  # Every Monday at 8:00 AM
            is_active=True,
            artifacts_config={
                "files": [
                    {
                        "name": "sales_report_{execution_id}.xlsx",
                        "type": "excel", 
                        "description": "Отчет по продажам"
                    }
                ]
            },
            variables={
                "period_days": 7,
                "include_forecast": True
            }
        )
        
        session.add(debtors_report)
        session.add(sales_report)
        
        await session.commit()
        
        print("Sample reports added successfully!")
        print(f"- {debtors_report.name} (ID: {debtors_report.id})")
        print(f"- {sales_report.name} (ID: {sales_report.id})")


async def main():
    """Main function."""
    try:
        await init_database()
        print("\nDatabase initialization completed successfully!")
        print(f"Database URL: {settings.database_url}")
        print(f"Jupyter notebooks path: {settings.jupyter_notebooks_path}")
        print(f"Output path: {settings.jupyter_output_path}")
    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
