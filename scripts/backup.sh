#!/bin/sh
# TR-O-06: dump the database into backup/scheduled and delete dumps there older than BACKUP_KEEP_DAYS (default 14).
# Run it from the repository folder, e.g. daily from cron:  0 2 * * * cd /opt/lms && scripts/backup.sh
# A restore brings back data a student has since had erased: see "Backup and restore" in the README.
set -eu
dir=${BACKUP_DIR:-backup/scheduled}
keep=${BACKUP_KEEP_DAYS:-14}
mkdir -p "$dir"
file="$dir/lms-$(date +%Y-%m-%d-%H%M%S).dump"
trap 'rm -f "$file.part"' EXIT
docker compose exec -T db pg_dump -U lms_owner -Fc lms > "$file.part"
[ -s "$file.part" ] || { echo "backup is empty" >&2; exit 1; }
mv "$file.part" "$file"
find "$dir" -name 'lms-*.dump' -mtime +"$keep" -delete
echo "$file"
