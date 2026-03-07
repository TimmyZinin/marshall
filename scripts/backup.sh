#!/bin/bash
# Marshall DB backup — runs daily via cron
# Cron: 0 3 * * * /opt/marshall/scripts/backup.sh

BACKUP_DIR="/opt/marshall/backups"
CONTAINER="marshall-db-1"
DB_NAME="marshall"
DB_USER="marshall"
KEEP_DAYS=7

mkdir -p "$BACKUP_DIR"
FILENAME="$BACKUP_DIR/marshall_$(date +%Y%m%d_%H%M%S).sql.gz"

docker exec "$CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FILENAME"

if [ $? -eq 0 ]; then
    echo "$(date): Backup OK — $FILENAME ($(du -h "$FILENAME" | cut -f1))"
    # Remove backups older than KEEP_DAYS
    find "$BACKUP_DIR" -name "marshall_*.sql.gz" -mtime +$KEEP_DAYS -delete
else
    echo "$(date): Backup FAILED"
    exit 1
fi
