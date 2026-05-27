"""
Service for storing and retrieving validation test results.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import ValidationRun, TestResult, UserSubscription


async def store_validation_results(
    session: AsyncSession,
    *,
    api_key: str | None = None,
    owner_email: str | None = None,
    test_packs: list[str],
    coverage_data: dict[str, Any],
    workbook_name: str | None = None,
    sheet_name: str | None = None,
    range_address: str | None = None,
    total_rows: int = 0,
    total_cells: int = 0,
    failed_cells: int = 0,
    passed_cells: int = 0,
    status: str = "completed",
    error_message: str | None = None,
) -> ValidationRun:
    """
    Store validation run results in the database.
    
    Args:
        session: Database session
        api_key: API key used for the request (will be hashed)
        test_packs: List of test pack names used
        coverage_data: Coverage report from validation
        workbook_name: Name of the workbook (if available)
        sheet_name: Name of the sheet (if available)
        range_address: Range address validated
        total_rows: Total data rows validated
        total_cells: Total cells validated
        failed_cells: Number of cells with failures
        passed_cells: Number of cells that passed
        status: Run status (completed, error, partial)
        error_message: Error message if status is error
        
    Returns:
        The created ValidationRun record
    """
    # Resolve user by email first (primary auth mode), else API key fallback
    api_key_hash = None
    user_id = None

    if owner_email:
        normalized_email = owner_email.strip().lower()
        if normalized_email:
            result = await session.execute(
                select(UserSubscription).where(func.lower(UserSubscription.email) == normalized_email)
            )
            user = result.scalar_one_or_none()
            if user:
                user_id = user.id
                api_key_hash = user.api_key_hash
    
    if api_key and not user_id:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        # Try to find the user
        result = await session.execute(
            select(UserSubscription).where(UserSubscription.api_key_hash == api_key_hash)
        )
        user = result.scalar_one_or_none()
        if user:
            user_id = user.id
    
    # Create the validation run
    validation_run = ValidationRun(
        user_id=user_id,
        api_key_hash=api_key_hash,
        timestamp=datetime.now(timezone.utc),
        workbook_name=workbook_name,
        sheet_name=sheet_name,
        range_address=range_address,
        test_packs=",".join(test_packs),
        total_rows=total_rows,
        total_cells=total_cells,
        failed_cells=failed_cells,
        passed_cells=passed_cells,
        status=status,
        error_message=error_message,
    )
    
    session.add(validation_run)
    await session.flush()  # Get the ID
    
    # Extract and store individual test results from coverage data
    packs_coverage = coverage_data.get("packs", {})
    
    for pack_name, pack_data in packs_coverage.items():
        tests = pack_data.get("tests", {})
        
        for test_name, test_data in tests.items():
            test_result = TestResult(
                validation_run_id=validation_run.id,
                test_pack=pack_name,
                test_name=test_name,
                test_description=test_data.get("description"),
                target_columns=",".join(test_data.get("targetColumns", [])),
                severity=test_data.get("severity", "ERROR"),
                severity_weight=test_data.get("severityWeight", 2),
                evaluated_rows=test_data.get("evaluatedRows", 0),
                passed_rows=test_data.get("passedRows", 0),
                failed_rows=test_data.get("failedRows", 0),
                failed_refs=list(test_data.get("failedRefs", [])) if test_data.get("failedRefs") else None,
            )
            session.add(test_result)
    
    await session.commit()
    await session.refresh(validation_run)
    
    return validation_run


async def get_validation_history(
    session: AsyncSession,
    *,
    api_key: str | None = None,
    owner_email: str | None = None,
    user_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ValidationRun]:
    """
    Get validation run history for a user.
    
    Args:
        session: Database session
        api_key: Filter by API key
        user_id: Filter by user ID
        limit: Maximum number of results
        offset: Offset for pagination
        
    Returns:
        List of ValidationRun records with test results
    """
    query = select(ValidationRun).options(
        selectinload(ValidationRun.test_results)
    ).order_by(desc(ValidationRun.timestamp))
    
    if owner_email:
        query = query.join(UserSubscription, ValidationRun.user_id == UserSubscription.id)
        query = query.where(func.lower(UserSubscription.email) == owner_email.strip().lower())
    elif api_key:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        query = query.where(ValidationRun.api_key_hash == api_key_hash)
    elif user_id:
        query = query.where(ValidationRun.user_id == user_id)
    
    query = query.limit(limit).offset(offset)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_validation_run(
    session: AsyncSession,
    run_id: int,
) -> ValidationRun | None:
    """
    Get a specific validation run by ID.
    
    Args:
        session: Database session
        run_id: Validation run ID
        
    Returns:
        ValidationRun record or None
    """
    result = await session.execute(
        select(ValidationRun)
        .options(selectinload(ValidationRun.test_results))
        .where(ValidationRun.id == run_id)
    )
    return result.scalar_one_or_none()


async def get_test_statistics(
    session: AsyncSession,
    *,
    api_key: str | None = None,
    owner_email: str | None = None,
    user_id: int | None = None,
    test_pack: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """
    Get aggregated test statistics for analytics.
    
    Args:
        session: Database session
        api_key: Filter by API key
        user_id: Filter by user ID
        test_pack: Filter by test pack name
        days: Number of days to look back
        
    Returns:
        Dictionary with aggregated statistics
    """
    from datetime import timedelta
    from sqlalchemy import func
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Build base query for validation runs
    runs_query = select(ValidationRun).where(ValidationRun.timestamp >= cutoff)
    
    if owner_email:
        runs_query = runs_query.join(UserSubscription, ValidationRun.user_id == UserSubscription.id)
        runs_query = runs_query.where(func.lower(UserSubscription.email) == owner_email.strip().lower())
    elif api_key:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        runs_query = runs_query.where(ValidationRun.api_key_hash == api_key_hash)
    elif user_id:
        runs_query = runs_query.where(ValidationRun.user_id == user_id)
    
    result = await session.execute(runs_query)
    runs = list(result.scalars().all())
    
    # Calculate statistics
    total_runs = len(runs)
    total_cells = sum(r.total_cells for r in runs)
    total_failed = sum(r.failed_cells for r in runs)
    total_passed = sum(r.passed_cells for r in runs)
    
    # Get test-level stats
    test_stats: dict[str, dict[str, int]] = {}
    
    for run in runs:
        # Need to load test results
        await session.refresh(run, ["test_results"])
        
        for test in run.test_results:
            if test_pack and test.test_pack != test_pack:
                continue
                
            key = f"{test.test_pack}.{test.test_name}"
            if key not in test_stats:
                test_stats[key] = {
                    "evaluated": 0,
                    "passed": 0,
                    "failed": 0,
                    "severity": test.severity,
                }
            
            test_stats[key]["evaluated"] += test.evaluated_rows
            test_stats[key]["passed"] += test.passed_rows
            test_stats[key]["failed"] += test.failed_rows
    
    return {
        "period_days": days,
        "total_runs": total_runs,
        "total_cells": total_cells,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "pass_rate": (total_passed / total_cells * 100) if total_cells > 0 else 0,
        "tests": test_stats,
    }
