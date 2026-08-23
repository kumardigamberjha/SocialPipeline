#!/usr/bin/env bash
#
# Snapshot the legacy SQLite databases before the Postgres cutover.
#
# The -wal sidecar routinely holds more recent data than the main file (at the
# time of writing nexus.db-wal was 4.1 MB against a 3.3 MB nexus.db), so a plain
# `cp` loses whatever has not been checkpointed yet. Checkpoint first, then copy.
#
# Usage:  ./scripts/backup_sqlite.sh
# Output: data/backup/<UTC timestamp>/{nexus.db,content_tracker.db}
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="data/backup/${STAMP}"
mkdir -p "$DEST"

for DB in data/nexus.db data/content_tracker.db; do
    if [[ ! -f "$DB" ]]; then
        echo "skip   $DB (not present)"
        continue
    fi

    # Checkpoint through Python: the sqlite3 CLI is not installed on this box,
    # but the stdlib module is always available.
    python3 - "$DB" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
conn = sqlite3.connect(path)
try:
    # TRUNCATE folds the WAL back into the main file and resets it to zero
    # length, so the single-file copy below is complete.
    busy, log_pages, checkpointed = conn.execute(
        "PRAGMA wal_checkpoint(TRUNCATE);"
    ).fetchone()
    if busy:
        raise SystemExit(
            f"{path}: checkpoint blocked by another connection — "
            "stop the API and workers, then retry."
        )
    print(f"       checkpointed {checkpointed}/{log_pages} WAL pages")
finally:
    conn.close()
PY

    cp "$DB" "$DEST/"
    echo "backup $DB -> $DEST/$(basename "$DB")"
done

# Record what was in there, so the row counts stay verifiable after the cutover.
python3 - "$DEST" <<'PY'
import pathlib
import sqlite3
import sys

dest = pathlib.Path(sys.argv[1])
lines = []
for db in sorted(dest.glob("*.db")):
    lines.append(f"=== {db.name} ===")
    conn = sqlite3.connect(db)
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        for table in tables:
            count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            lines.append(f"  {table:34} {count}")
    finally:
        conn.close()

report = "\n".join(lines) + "\n"
(dest / "INVENTORY.txt").write_text(report)
print(report, end="")
PY

echo
echo "Backup complete: $DEST"
