from __future__ import annotations

import pytest
from sqlalchemy import select

from backend.app.config import Settings
from backend.db.models import (
    StructuredColumn,
    StructuredQueryLog,
    StructuredRow,
    StructuredTable,
    Tenant,
)
from backend.structured.query_service import (
    GuardViolation,
    build_query_service,
)


def _seed_table(session, tenant: Tenant) -> StructuredTable:
    table = StructuredTable(
        tenant_id=tenant.id,
        table_name="employees",
        display_name="Employees",
        source_path="/tmp/employees.csv",
        version=1,
        status="ready",
    )
    session.add(table)
    session.flush()

    columns = [
        StructuredColumn(
            table_id=table.id,
            column_order=1,
            name="id",
            slug="id",
            data_type="integer",
            is_primary_key=True,
            nullable=False,
        ),
        StructuredColumn(
            table_id=table.id,
            column_order=2,
            name="name",
            slug="name",
            data_type="string",
            is_primary_key=False,
            nullable=False,
        ),
    ]
    session.add_all(columns)

    rows = [
        StructuredRow(table_id=table.id, row_index=index, payload=row)
        for index, row in enumerate(
            [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
                {"id": 3, "name": "Charlie"},
            ]
        )
    ]
    session.add_all(rows)
    session.commit()
    return table


@pytest.mark.asyncio
async def test_execute_allows_safe_select(db_session, settings_override: Settings):
    tenant = Tenant(name="Acme", slug="acme")
    db_session.add(tenant)
    db_session.commit()

    _seed_table(db_session, tenant)

    service = build_query_service(settings_override, db_session)
    result = service.execute("SELECT id, name FROM employees LIMIT 10", tenant.id, "employees")

    assert result.row_count == 3
    assert result.columns[0].name == "id"
    assert result.rows[0].values["name"] == "Alice"

    log = db_session.execute(select(StructuredQueryLog).order_by(StructuredQueryLog.created_at.desc())).scalar_one()
    assert log.status == "allowed"
    assert log.row_count == 3


@pytest.mark.asyncio
async def test_execute_blocks_update(db_session, settings_override: Settings):
    tenant = Tenant(name="Acme", slug="acme")
    db_session.add(tenant)
    db_session.commit()

    _seed_table(db_session, tenant)

    service = build_query_service(settings_override, db_session)

    with pytest.raises(GuardViolation):
        service.execute("UPDATE employees SET name='Alice'", tenant.id, "employees")

    log = db_session.execute(select(StructuredQueryLog).order_by(StructuredQueryLog.created_at.desc())).scalar_one()
    assert log.status == "blocked"


@pytest.mark.asyncio
async def test_execute_requires_limit(db_session, settings_override: Settings):
    tenant = Tenant(name="Acme", slug="acme")
    db_session.add(tenant)
    db_session.commit()

    _seed_table(db_session, tenant)
    service = build_query_service(settings_override, db_session)

    with pytest.raises(GuardViolation):
        service.execute("SELECT * FROM employees", tenant.id, "employees")

    log = db_session.execute(select(StructuredQueryLog).order_by(StructuredQueryLog.created_at.desc())).scalar_one()
    assert log.status == "blocked"


@pytest.mark.asyncio
async def test_execute_logs_error_on_exception(db_session, settings_override: Settings, monkeypatch):
    tenant = Tenant(name="Acme", slug="acme")
    db_session.add(tenant)
    db_session.commit()

    _seed_table(db_session, tenant)
    service = build_query_service(settings_override, db_session)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_execute_sqlite", boom)

    with pytest.raises(RuntimeError):
        service.execute("SELECT id FROM employees LIMIT 5", tenant.id, "employees")

    log = db_session.execute(select(StructuredQueryLog).order_by(StructuredQueryLog.created_at.desc())).scalar_one()
    assert log.status == "error"
    assert log.reason is not None
