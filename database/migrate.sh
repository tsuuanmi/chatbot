#!/bin/sh

set -eu

: "${PGHOST:?PGHOST is required}"
: "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${POSTGRES_PASSWORD_FILE:?POSTGRES_PASSWORD_FILE is required}"

if [ ! -r "$POSTGRES_PASSWORD_FILE" ]; then
    echo "PostgreSQL password file is not readable" >&2
    exit 1
fi

PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"
export PGPASSWORD

psql_common() {
    psql \
        -X \
        -v ON_ERROR_STOP=1 \
        -h "$PGHOST" \
        -p "$PGPORT" \
        -U "$PGUSER" \
        -d "$PGDATABASE" \
        "$@"
}

psql_common <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    name text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT now()
);
SQL

for migration in /database/migrations/*.sql; do
    [ -f "$migration" ] || continue

    name="$(basename "$migration")"

    case "$name" in
        [0-9][0-9][0-9]_*.sql)
            ;;
        *)
            echo "Invalid migration filename: $name" >&2
            exit 1
            ;;
    esac

    version="${name%%_*}"

    applied="$(
        psql_common \
            -At \
            -v migration_version="$version" <<'SQL'
SELECT 1
FROM schema_migrations
WHERE version = :'migration_version'
LIMIT 1;
SQL
    )"

    if [ "$applied" = "1" ]; then
        echo "Already applied: $name"
        continue
    fi

    echo "Applying: $name"

    {
        echo "BEGIN;"
        cat "$migration"
        echo
        echo "INSERT INTO schema_migrations (version, name)"
        echo "VALUES (:'migration_version', :'migration_name');"
        echo "COMMIT;"
    } |
        psql_common \
            -v migration_version="$version" \
            -v migration_name="$name"

    echo "Applied: $name"
done
