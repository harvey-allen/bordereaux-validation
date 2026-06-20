"""Pydantic schemas for the Rules Engine domain."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RulesEngineRule(BaseModel):
    pack: str
    rule_id: str
    target_column: str
    description: str
    severity: str
    test_type: Optional[str] = None


class RulesEngineResponse(BaseModel):
    packs: list[str]
    rules: list[RulesEngineRule]
