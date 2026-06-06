#!/usr/bin/env python3
"""
Quick test script for the exception management API.

Usage:
    python3 test_exceptions_api.py

Prerequisites:
    - Backend running on localhost:8000
    - Database initialized
    - User registered with X-Excel-User-Email header
"""

import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test-exception-user@example.com"

headers = {
    "X-Excel-User-Email": TEST_EMAIL,
    "Content-Type": "application/json",
}


async def test_create_exception():
    """Test creating an exception."""
    print("\n=== Testing CREATE Exception ===")
    async with httpx.AsyncClient(timeout=10) as client:
        payload = {
            "exception_id": "EXC-001",
            "description": "Test exception for validation",
            "linked_field": "Unique Market Reference (UMR)",
            "linked_umr": "B1234A23",
            "status": "to do",
        }
        
        response = await client.post(
            f"{BASE_URL}/api/v1/exceptions",
            json=payload,
            headers=headers,
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("✅ CREATE successful")
            return response.json()
        else:
            print("❌ CREATE failed")
            return None


async def test_list_exceptions():
    """Test listing exceptions."""
    print("\n=== Testing LIST Exceptions ===")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/exceptions",
            headers=headers,
        )
        
        print(f"Status: {response.status_code}")
        data = response.json()
        exceptions = data.get("exceptions", [])
        print(f"Found {len(exceptions)} exception(s)")
        
        for exc in exceptions:
            print(f"  - {exc['exception_id']}: {exc['description']} ({exc['status']})")
        
        if response.status_code == 200:
            print("✅ LIST successful")
            return exceptions
        else:
            print("❌ LIST failed")
            return []


async def test_update_exception():
    """Test updating an exception."""
    print("\n=== Testing UPDATE Exception ===")
    async with httpx.AsyncClient(timeout=10) as client:
        payload = {
            "status": "in progress",
            "description": "Updated description for testing",
        }
        
        response = await client.put(
            f"{BASE_URL}/api/v1/exceptions/EXC-001",
            json=payload,
            headers=headers,
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("✅ UPDATE successful")
            return response.json()
        else:
            print("❌ UPDATE failed")
            return None


async def test_filter_by_linked_field():
    """Test filtering exceptions by linked_field."""
    print("\n=== Testing FILTER by linked_field ===")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/exceptions?linked_field=Unique%20Market%20Reference%20(UMR)",
            headers=headers,
        )
        
        print(f"Status: {response.status_code}")
        data = response.json()
        exceptions = data.get("exceptions", [])
        print(f"Found {len(exceptions)} exception(s) with linked_field='Unique Market Reference (UMR)'")
        
        if response.status_code == 200:
            print("✅ FILTER successful")
        else:
            print("❌ FILTER failed")


async def test_duplicate_exception():
    """Test creating duplicate exception (should fail)."""
    print("\n=== Testing DUPLICATE prevention ===")
    async with httpx.AsyncClient(timeout=10) as client:
        payload = {
            "exception_id": "EXC-001",
            "description": "This should fail - duplicate ID",
            "status": "to do",
        }
        
        response = await client.post(
            f"{BASE_URL}/api/v1/exceptions",
            json=payload,
            headers=headers,
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 409:
            print("✅ DUPLICATE prevention working (409 Conflict)")
        else:
            print("❌ DUPLICATE prevention failed")


async def test_delete_exception():
    """Test deleting an exception."""
    print("\n=== Testing DELETE Exception ===")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.delete(
            f"{BASE_URL}/api/v1/exceptions/EXC-001",
            headers=headers,
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("✅ DELETE successful")
        else:
            print("❌ DELETE failed")


async def test_nonexistent_exception():
    """Test accessing non-existent exception (should fail)."""
    print("\n=== Testing NONEXISTENT exception handling ===")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.delete(
            f"{BASE_URL}/api/v1/exceptions/NONEXISTENT",
            headers=headers,
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 404:
            print("✅ NONEXISTENT handling working (404 Not Found)")
        else:
            print("❌ NONEXISTENT handling failed")


async def run_all_tests():
    """Run all tests in sequence."""
    print("=" * 60)
    print("Exception Management API Test Suite")
    print("=" * 60)
    
    try:
        # Create
        await test_create_exception()
        
        # List
        exceptions = await test_list_exceptions()
        
        # Update
        if exceptions:
            await test_update_exception()
        
        # Filter
        await test_filter_by_linked_field()
        
        # Duplicate
        await test_duplicate_exception()
        
        # Delete
        await test_delete_exception()
        
        # Nonexistent
        await test_nonexistent_exception()
        
        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
