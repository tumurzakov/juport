#!/usr/bin/env python3
"""Script to check report configuration in database."""
import asyncio
import sys
sys.path.append('.')
from app.database import async_session_factory
from app.models import Report
from sqlalchemy import select

async def check_report():
    async with async_session_factory() as session:
        result = await session.execute(select(Report).where(Report.name.like('%Должники%')))
        reports = result.scalars().all()
        
        if not reports:
            print("No reports found with 'Должники' in name")
            # Let's check all reports
            result = await session.execute(select(Report))
            all_reports = result.scalars().all()
            print(f"Total reports in database: {len(all_reports)}")
            for report in all_reports:
                print(f"- {report.name} (ID: {report.id})")
        else:
            for report in reports:
                print(f'Report: {report.name}')
                print(f'ID: {report.id}')
                print(f'Notebook: {report.notebook_path}')
                print(f'Artifacts config: {report.artifacts_config}')
                print(f'Variables: {report.variables}')
                print('---')

if __name__ == "__main__":
    asyncio.run(check_report())
