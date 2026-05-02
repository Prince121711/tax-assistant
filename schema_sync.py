"""
Helpers for bringing older databases in sync with the current ORM models.
"""

from sqlalchemy import inspect, text


def ensure_legacy_schema(engine) -> list[str]:
    """
    Add columns that older databases may be missing.

    SQLAlchemy's `create_all()` creates missing tables, but it does not alter
    existing ones. This keeps older MySQL or SQLite databases aligned with the
    current ORM models.
    """
    created_at_definitions = {
        "mysql": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "sqlite": "DATETIME",
    }
    default_definition = created_at_definitions.get(engine.dialect.name, "DATETIME")
    required_columns = {
        "users": {"created_at": default_definition},
        "income": {"created_at": default_definition},
        "expense": {"created_at": default_definition},
    }

    applied_changes: list[str] = []
    with engine.begin() as connection:
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())

        for table_name, columns in required_columns.items():
            if table_name not in existing_tables:
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name in existing_columns:
                    continue

                connection.execute(
                    text(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {ddl}")
                )
                applied_changes.append(f"{table_name}.{column_name}")

    return applied_changes
