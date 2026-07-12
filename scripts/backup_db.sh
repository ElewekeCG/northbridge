#!/usr/bin/env bash
# scripts/backup_db.sh
# Northbridge Commerce — PostgreSQL backup script
#
# Creates a pg_dump of northbridge_db, stores it locally under
# /tmp/northbridge-backups/, and uploads to S3.
#
# Usage:
#   bash scripts/backup_db.sh
#
# Required env vars (read from .env if not already set):
#   POSTGRES_PASSWORD, BACKUP_S3_BUCKET, AWS_REGION
#
# Install as daily cron:
#   0 2 * * * cd /home/ec2-user/northbridge && bash scripts/backup_db.sh >> /var/log/northbridge-backup.log 2>&1

set -euo pipefail

# ── Load .env if vars not already set ────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

# ── Config ────────────────────────────────────────────────────────────────────
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/northbridge-backups"
BACKUP_FILE="northbridge_db_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"
S3_KEY="backups/postgres/${BACKUP_FILE}"

POSTGRES_USER="${POSTGRES_USER:-northbridge}"
POSTGRES_DB="${POSTGRES_DB:-northbridge_db}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting backup of ${POSTGRES_DB}"

# ── Create local backup directory ─────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

# ── Run pg_dump inside the postgres container ─────────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Running pg_dump..."
docker exec northbridge-postgres-1 \
  pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  --no-password \
  | gzip > "$BACKUP_PATH"

BACKUP_SIZE=$(du -sh "$BACKUP_PATH" | cut -f1)
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Local backup created: ${BACKUP_PATH} (${BACKUP_SIZE})"

# ── Upload to S3 ──────────────────────────────────────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Uploading to s3://${BACKUP_S3_BUCKET}/${S3_KEY}..."
aws s3 cp "$BACKUP_PATH" "s3://${BACKUP_S3_BUCKET}/${S3_KEY}" \
  --region "${AWS_REGION:-eu-west-2}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] S3 upload complete: s3://${BACKUP_S3_BUCKET}/${S3_KEY}"

# ── Verify S3 upload ──────────────────────────────────────────────────────────
S3_SIZE=$(aws s3 ls "s3://${BACKUP_S3_BUCKET}/${S3_KEY}" --region "${AWS_REGION:-eu-west-2}" | awk '{print $3}')
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] S3 object size: ${S3_SIZE} bytes"

# ── Clean up local backups older than 7 days ──────────────────────────────────
find "$BACKUP_DIR" -name "northbridge_db_*.sql.gz" -mtime +7 -delete
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Cleaned up local backups older than 7 days"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backup complete: ${BACKUP_FILE}"