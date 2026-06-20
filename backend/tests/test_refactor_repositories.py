from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.repositories.configuration.pack_config_repository import PackConfigRepository
from app.repositories.results.results_repository import ResultsRepository
from app.repositories.shared.sheet_key_repository import SheetKeyRepository


class FakeResult:
    def __init__(self, *, item=None, items=None, row=None):
        self._item = item
        self._items = items
        self._row = row

    def scalar_one_or_none(self):
        return self._item

    def scalar_one(self):
        return self._item

    def scalars(self):
        return self

    def all(self):
        return self._items or []

    def first(self):
        return self._row

    def scalar(self):
        return self._item


def test_pack_config_repository_get_config_returns_existing_config(monkeypatch):
    fake_sheet_key = SimpleNamespace(id=123)
    fake_config = SimpleNamespace(config_json={"alpha": 1})
    db = SimpleNamespace(execute=AsyncMock(return_value=FakeResult(item=fake_config)))

    async def fake_find(session, *, organisation_id, workbook_name, sheet_name, test_pack):
        return fake_sheet_key

    monkeypatch.setattr(SheetKeyRepository, "find", fake_find)

    result = asyncio.run(
        PackConfigRepository.get_config(
            db,
            organisation_id=1,
            user_id=2,
            workbook_name="Book.xlsx",
            sheet_name="Sheet 1",
            test_pack="risk_and_premium",
        )
    )

    assert result == {"alpha": 1}
    db.execute.assert_awaited_once()


def test_pack_config_repository_upsert_config_creates_record(monkeypatch):
    fake_sheet_key = SimpleNamespace(id=456)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=FakeResult(item=None)),
        add=MagicMock(),
        commit=AsyncMock(),
    )

    async def fake_get_or_create(session, *, organisation_id, workbook_name, sheet_name, test_pack):
        return fake_sheet_key

    monkeypatch.setattr(SheetKeyRepository, "get_or_create", fake_get_or_create)

    result = asyncio.run(
        PackConfigRepository.upsert_config(
            db,
            organisation_id=1,
            user_id=2,
            workbook_name="Book.xlsx",
            sheet_name="Sheet 1",
            test_pack="risk_and_premium",
            pack_config={"beta": 2},
        )
    )

    assert result == {"beta": 2}
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    created = db.add.call_args.args[0]
    assert created.sheet_key_id == 456
    assert created.config_json == {"beta": 2}


def test_results_repository_get_latest_run_for_scope_filters_by_user_id():
    session = SimpleNamespace(execute=AsyncMock(return_value=FakeResult(item=SimpleNamespace(id=99))))

    result = asyncio.run(
        ResultsRepository.get_latest_run_for_scope(
            session,
            sheet_name="Sheet 1",
            workbook_name="Book.xlsx",
            user_id=5,
            api_key_hash=None,
        )
    )

    assert result.id == 99
    session.execute.assert_awaited_once()
