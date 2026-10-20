#!/bin/sh
# TR-O-06: restore the newest scheduled dump into a scratch database and compare row counts with the live one.
# The live database is only read. A table that is empty in the dump but not in the live database fails the check;
# counts differ legitimately when rows were added or erased after the dump was taken.
set -eu
dir=${BACKUP_DIR:-backup/scheduled}
scratch=lms_restorecheck
latest=$(ls -1t "$dir"/lms-*.dump | head -n 1)
sql() { docker compose exec -T db psql -U lms_owner -v ON_ERROR_STOP=1 -tA "$@"; }
trap 'sql -d postgres -c "DROP DATABASE IF EXISTS $scratch" >/dev/null' EXIT
sql -d postgres -c "DROP DATABASE IF EXISTS $scratch" -c "CREATE DATABASE $scratch" >/dev/null
docker compose exec -T db pg_restore -U lms_owner -d "$scratch" --no-owner --exit-on-error < "$latest"
echo "restored $latest"
status=0
for table in users courses problems submissions mastery_events consents; do
  live=$(sql -d lms -c "SELECT count(*) FROM $table")
  dump=$(sql -d "$scratch" -c "SELECT count(*) FROM $table")
  echo "$table dump=$dump live=$live"
  if [ "$dump" -eq 0 ] && [ "$live" -gt 0 ]; then status=1; fi
done
exit $status
