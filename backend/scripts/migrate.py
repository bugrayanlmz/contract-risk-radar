"""Idempotent queue-schema bootstrap/upgrades, followed by Alembic.

API and worker must be stopped while this runs.
"""

import subprocess
import sys
from pathlib import Path

import psycopg
from procrastinate.schema import SchemaManager

from app.config import get_settings


def migrate_queue(conninfo: str):
    migrations = sorted(Path(SchemaManager.get_migrations_path()).glob("*.sql"))
    with psycopg.connect(conninfo) as connection:
        # Serialize concurrent migration containers using a transaction-level lock.
        connection.execute("SELECT pg_advisory_xact_lock(741923)")
        existing = connection.execute("SELECT to_regclass('public.procrastinate_jobs')").fetchone()[
            0
        ]
        ledger = connection.execute(
            "SELECT to_regclass('public.radar_queue_migrations')"
        ).fetchone()[0]
        if existing and not ledger:
            raise RuntimeError(
                "Existing unmanaged Procrastinate schema: apply/record its migrations explicitly before startup."
            )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS radar_queue_migrations (name TEXT PRIMARY KEY)"
        )
        if not existing:
            connection.execute(SchemaManager.get_schema())
            for path in migrations:
                connection.execute(
                    "INSERT INTO radar_queue_migrations(name) VALUES (%s)", [path.name]
                )
        else:
            applied = {
                row[0] for row in connection.execute("SELECT name FROM radar_queue_migrations")
            }
            for path in migrations:
                if path.name not in applied:
                    connection.execute(path.read_text())
                    connection.execute(
                        "INSERT INTO radar_queue_migrations(name) VALUES (%s)", [path.name]
                    )


if __name__ == "__main__":
    migrate_queue(get_settings().queue_conninfo)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
