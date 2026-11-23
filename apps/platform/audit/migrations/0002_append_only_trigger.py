"""On PostgreSQL, make audit_events append-only inside the database itself.

Django already refuses to change or delete an event; this trigger also stops raw
SQL and other tools. It raises ``restrict_violation`` (23001), which Django turns
into ``IntegrityError``. SQLite (local development until build 01) gets no
trigger: its ``flush`` command deletes rows one table at a time and would stop.
PostgreSQL's ``flush`` uses TRUNCATE, which row triggers do not see.
"""

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE = """
CREATE FUNCTION audit_events_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;
CREATE TRIGGER audit_events_append_only
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();
"""

DROP = """
DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;
DROP FUNCTION IF EXISTS audit_events_append_only();
"""


def _on_postgres(sql: str):  # type: ignore[no-untyped-def]
    def run(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
        if schema_editor.connection.vendor == "postgresql":
            # No parameters, so the driver leaves the % in the message alone.
            schema_editor.execute(sql, params=None)

    return run


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunPython(_on_postgres(CREATE), _on_postgres(DROP))]
