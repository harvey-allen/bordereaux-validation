#!/usr/bin/env python3
"""
Quick test for the exception analytics endpoint.
"""
import asyncio
import sys
sys.path.insert(0, '/Users/harvey/Documents/Portfolio/axios/bordereaux-validation')

from backend.app.database import ValidationResultVersion, UserSubscription
from backend.app.exceptions_service import exception_service
from sqlalchemy import select
from backend.app.database import async_session_maker

async def test():
    """Test the exception analytics logic"""
    async with async_session_maker() as session:
        # Get organisation 1 as test
        user_query = select(UserSubscription).limit(1)
        result = await session.execute(user_query)
        user = result.scalar_one_or_none()
        
        if not user:
            print("No users found in database")
            return
        
        print(f"Found user: {user.id}, org: {user.organisation_id}")
        
        # Test get_exceptions
        exceptions = await exception_service.get_exceptions(
            session,
            organisation_id=user.organisation_id,
        )
        print(f"Found {len(exceptions)} exceptions")
        for exc in exceptions:
            print(f"  - {exc.exception_id}: {exc.description}")
        
        # Test getting versions
        user_ids = [user.id]
        versions_query = select(ValidationResultVersion).where(
            ValidationResultVersion.user_id.in_(user_ids)
        )
        versions_result = await session.execute(versions_query)
        versions = versions_result.scalars().all()
        print(f"Found {len(versions)} validation result versions")
        
        # Count tags
        exception_tag_counts = {}
        for version in versions:
            tagged_cells = version.tagged_cells_json or []
            print(f"  Version {version.id}: {len(tagged_cells)} tagged cells")
            if isinstance(tagged_cells, list):
                for tagged_cell in tagged_cells:
                    if isinstance(tagged_cell, dict):
                        exc_id = str(tagged_cell.get("exception_id") or "").strip()
                        if exc_id:
                            exception_tag_counts[exc_id] = exception_tag_counts.get(exc_id, 0) + 1
                            print(f"    - Exception: {exc_id}")
        
        print(f"\nException tag counts: {exception_tag_counts}")

if __name__ == '__main__':
    asyncio.run(test())
