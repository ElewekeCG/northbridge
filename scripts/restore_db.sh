#!/usr/bin/env bash
# scripts/restore_db.sh
# Northbridge Commerce — PostgreSQL restore script
#
# Restores northbridge_db from either a local backup file or the
# latest backup from S3.
#
# Usage:
#   bash scripts/restore_db.sh --s3-latest          # pull latest from S3
#   bash scripts/restore_db.sh --file /path/to.sql.gz  # restore local file
#
# WARNING: This drops and recreates the northbridge_db database.
# All existing data will be lost. Only run this in a recovery scenario.

set -euo pipefail

# ── Load .env ─────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  while IFS='=' read -r key value; do
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue
    export "$key"="$value" 2>/dev/null || true
  done < "$PROJECT_DIR/.env"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-northbridge}"
POSTGRES_DB="${POSTGRES_DB:-northbridge_db}"
BACKUP_DIR="/tmp/northbridge-backups"

# ── Parse arguments ───────────────────────────────────────────────────────────
MODE=""
LOCAL_FILE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --s3-latest)
      MODE="s3-latest"
      shift
      ;;
    --file)
      MODE="file"
      LOCAL_FILE="$2"
      shift 2
      ;;
    *)
      echo "Usage: $0 --s3-latest | --file /path/to/backup.sql.gz"
      exit 1
      ;;
  esac
done

if [ -z "$MODE" ]; then
  echo "Usage: $0 --s3-latest | --file /path/to/backup.sql.gz"
  exit 1
fi

# ── Fetch from S3 if requested ────────────────────────────────────────────────
if [ "$MODE" = "s3-latest" ]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Finding latest backup in s3://${BACKUP_S3_BUCKET}/backups/postgres/"

  LATEST_KEY=$(aws s3 ls "s3://${BACKUP_S3_BUCKET}/backups/postgres/" \
    --region "${AWS_REGION:-eu-west-2}" \
    | sort | tail -1 | awk '{print $4}')

  if [ -z "$LATEST_KEY" ]; then
    echo "ERROR: No backups found in s3://${BACKUP_S3_BUCKET}/backups/postgres/"
    exit 1
  fi

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Latest backup: ${LATEST_KEY}"

  mkdir -p "$BACKUP_DIR"
  LOCAL_FILE="${BACKUP_DIR}/${LATEST_KEY}"

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Downloading from S3..."
  aws s3 cp "s3://${BACKUP_S3_BUCKET}/backups/postgres/${LATEST_KEY}" "$LOCAL_FILE" \
    --region "${AWS_REGION:-eu-west-2}"

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Downloaded to: ${LOCAL_FILE}"
fi

# ── Validate backup file ──────────────────────────────────────────────────────
if [ ! -f "$LOCAL_FILE" ]; then
  echo "ERROR: Backup file not found: ${LOCAL_FILE}"
  exit 1
fi

FILE_SIZE=$(du -sh "$LOCAL_FILE" | cut -f1)
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Restoring from: ${LOCAL_FILE} (${FILE_SIZE})"

# ── Confirm before proceeding ─────────────────────────────────────────────────
echo ""
echo "WARNING: This will DROP and recreate ${POSTGRES_DB}. All existing data will be lost."
read -p "Type 'yes' to confirm: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted."
  exit 0
fi

# ── Stop services that use the database ───────────────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Stopping application services..."
cd "$PROJECT_DIR"
docker compose stop auth-service catalog-service inventory-service orders-service \
  payments-service notifications-service analytics-service

# ── Drop and recreate the database ───────────────────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Dropping and recreating ${POSTGRES_DB}..."
docker exec northbridge-postgres-1 psql -U "$POSTGRES_USER" -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();"
docker exec northbridge-postgres-1 psql -U "$POSTGRES_USER" -d postgres -c \
  "DROP DATABASE IF EXISTS ${POSTGRES_DB};"
docker exec northbridge-postgres-1 psql -U "$POSTGRES_USER" -d postgres -c \
  "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

# ── Restore ───────────────────────────────────────────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Restoring data..."
gunzip -c "$LOCAL_FILE" | docker exec -i northbridge-postgres-1 \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Restore complete."

# ── Restart application services ─────────────────────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Restarting application services..."
docker compose start auth-service catalog-service inventory-service orders-service \
  payments-service notifications-service analytics-service

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] All services restarted. Restore successful."