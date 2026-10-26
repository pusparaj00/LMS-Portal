#!/bin/sh
# TR-O-06, G-8: copy the newest scheduled dump to a place that is not this server, and check the copy by checksum.
# OFFSITE_TARGET is a folder on another disk or mount (/mnt/usb/lms) or user@host:folder (copied with scp, so the key or
# agent for that host must already work). Run after backup.sh, e.g. from cron:  30 2 * * * cd /opt/lms && scripts/offsite-copy.sh
# An erased student's data returns if an old dump is restored: see "Backup and restore" in the README.
set -eu
dir=${BACKUP_DIR:-backup/scheduled}
target=${OFFSITE_TARGET:?set OFFSITE_TARGET to a folder or user@host:folder}
file=$(ls -t "$dir"/lms-*.dump 2>/dev/null | head -n 1)
[ -n "$file" ] || { echo "no dump in $dir; run scripts/backup.sh first" >&2; exit 1; }
name=$(basename "$file")
sum=$(sha256sum "$file" | cut -d' ' -f1)
case "$target" in
  *:*)
    host=${target%%:*}; remote=${target#*:}
    scp -q "$file" "$target/$name.part"
    copied=$(ssh "$host" "sha256sum '$remote/$name.part'" | cut -d' ' -f1)
    if [ "$copied" = "$sum" ]; then ssh "$host" "mv '$remote/$name.part' '$remote/$name'"
    else ssh "$host" "rm -f '$remote/$name.part'"; fi ;;
  *)
    mkdir -p "$target"
    cp "$file" "$target/$name.part"
    copied=$(sha256sum "$target/$name.part" | cut -d' ' -f1)
    if [ "$copied" = "$sum" ]; then mv "$target/$name.part" "$target/$name"
    else rm -f "$target/$name.part"; fi ;;
esac
[ "$copied" = "$sum" ] || { echo "the copy of $name does not match (checksum differs); it was not kept" >&2; exit 1; }
echo "$name copied to $target, sha256 $sum"
