"""On PostgreSQL, make terms_acceptances append-only inside the database itself.

The same pattern as the audit log (audit 0002): Django already refuses to change or
delete an acceptance; this trigger also stops raw SQL and other tools. SQLite gets no
trigger, because its ``flush`` deletes rows one by one and would stop.
"""

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE = """
CREATE FUNCTION terms_acceptances_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'terms_acceptances is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;
CREATE TRIGGER terms_acceptances_append_only
    BEFORE UPDATE OR DELETE ON terms_acceptances
    FOR EACH ROW EXECUTE FUNCTION terms_acceptances_append_only();
"""

DROP = """
DROP TRIGGER IF EXISTS terms_acceptances_append_only ON terms_acceptances;
DROP FUNCTION IF EXISTS terms_acceptances_append_only();
"""


def _on_postgres(sql: str):  # type: ignore[no-untyped-def]
    def run(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
        if schema_editor.connection.vendor == "postgresql":
            # No parameters, so the driver leaves the % in the message alone.
            schema_editor.execute(sql, params=None)

    return run


class Migration(migrations.Migration):
    dependencies = [("legal", "0001_initial")]

    operations = [migrations.RunPython(_on_postgres(CREATE), _on_postgres(DROP))]
