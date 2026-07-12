[ec2-user@ip-172-31-28-172 northbridge]$ bash scripts/backup_db.sh
[2026-07-12T14:27:18Z] Starting backup of northbridge_db
[2026-07-12T14:27:18Z] Running pg_dump...
[2026-07-12T14:27:18Z] Local backup created: /tmp/northbridge-backups/northbridge_db_20260712_142718.sql.gz (4.0K)
[2026-07-12T14:27:18Z] Uploading to s3://northbridge-db-backups/backups/postgres/northbridge_db_20260712_142718.sql.gz...
Completed 2.8 KiB/2.8 KiB (9.6 KiB/s) with 1 file(s) upload: ../../../tmp/northbridge-backups/northbridge_db_20260712_142718.sql.gz to s3://northbridge-db-backups/backups/postgres/northbridge_db_20260712_142718.sql.gz
[2026-07-12T14:27:19Z] S3 upload complete: s3://northbridge-db-backups/backups/postgres/northbridge_db_20260712_142718.sql.gz
[2026-07-12T14:27:20Z] S3 object size: 2836 bytes
[2026-07-12T14:27:20Z] Cleaned up local backups older than 7 days
[2026-07-12T14:27:20Z] Backup complete: northbridge_db_20260712_142718.sql.gz
[ec2-user@ip-172-31-28-172 northbridge]$ docker exec northbridge-postgres-1 psql -U northbridge -d northbridge_db -c \
  "INSERT INTO products (sku, name, description, price, stock, category) VALUES ('TEST-DR-001', 'DISASTER_RECOVERY_TEST_ROW', 'delete this after restore test', 0.01, 1, 'Test');"
INSERT 0 1
[ec2-user@ip-172-31-28-172 northbridge]$ bash scripts/backup_db.sh
[2026-07-12T14:28:04Z] Starting backup of northbridge_db
[2026-07-12T14:28:04Z] Running pg_dump...
[2026-07-12T14:28:04Z] Local backup created: /tmp/northbridge-backups/northbridge_db_20260712_142804.sql.gz (4.0K)
[2026-07-12T14:28:04Z] Uploading to s3://northbridge-db-backups/backups/postgres/northbridge_db_20260712_142804.sql.gz...
Completed 2.8 KiB/2.8 KiB (9.3 KiB/s) with 1 file(s) upload: ../../../tmp/northbridge-backups/northbridge_db_20260712_142804.sql.gz to s3://northbridge-db-backups/backups/postgres/northbridge_db_20260712_142804.sql.gz
[2026-07-12T14:28:05Z] S3 upload complete: s3://northbridge-db-backups/backups/postgres/northbridge_db_20260712_142804.sql.gz
[2026-07-12T14:28:06Z] S3 object size: 2913 bytes
[2026-07-12T14:28:06Z] Cleaned up local backups older than 7 days
[2026-07-12T14:28:06Z] Backup complete: northbridge_db_20260712_142804.sql.gz
[ec2-user@ip-172-31-28-172 northbridge]$ docker exec northbridge-postgres-1 psql -U northbridge -d northbridge_db -c \
  "DELETE FROM products WHERE sku = 'TEST-DR-001';"
DELETE 1
[ec2-user@ip-172-31-28-172 northbridge]$ docker exec northbridge-postgres-1 psql -U northbridge -d northbridge_db -c \
  "SELECT * FROM products WHERE sku = 'TEST-DR-001';" id | sku | name | description | price | stock | category | created_at 
----+-----+------+-------------+-------+-------+----------+------------
(0 rows)
[ec2-user@ip-172-31-28-172 northbridge]$ bash scripts/restore_db.sh --s3-latest
[2026-07-12T14:50:24Z] Finding latest backup in s3://northbridge-db-backups/backups/postgres/
[2026-07-12T14:50:25Z] Latest backup: northbridge_db_20260712_142804.sql.gz
[2026-07-12T14:50:25Z] Downloading from S3...
Completed 2.8 KiB/2.8 KiB (9.7 KiB/s) with 1 file(s) download: s3://northbridge-db-backups/backups/postgres/northbridge_db_20260712_142804.sql.gz to ../../../tmp/northbridge-backups/northbridge_db_20260712_142804.sql.gz
[2026-07-12T14:50:27Z] Downloaded to: /tmp/northbridge-backups/northbridge_db_20260712_142804.sql.gz
[2026-07-12T14:50:27Z] Restoring from: /tmp/northbridge-backups/northbridge_db_20260712_142804.sql.gz (4.0K)

WARNING: This will DROP and recreate northbridge_db. All existing data will be lost.
Type 'yes' to confirm: yes
[2026-07-12T14:50:31Z] Stopping application services...
WARN[0000] The "apr1" variable is not set. Defaulting to a blank string. 
WARN[0000] The "wcNmmRwU" variable is not set. Defaulting to a blank string. 
WARN[0000] The "nunCv" variable is not set. Defaulting to a blank string. 
WARN[0000] The "apr1" variable is not set. Defaulting to a blank string. 
WARN[0000] The "wcNmmRwU" variable is not set. Defaulting to a blank string. 
WARN[0000] The "nunCv" variable is not set. Defaulting to a blank string. 
WARN[0000] The "apr1" variable is not set. Defaulting to a blank string. 
WARN[0000] The "wcNmmRwU" variable is not set. Defaulting to a blank string. 
WARN[0000] The "nunCv" variable is not set. Defaulting to a blank string. 
WARN[0000] The "apr1" variable is not set. Defaulting to a blank string. 
WARN[0000] The "wcNmmRwU" variable is not set. Defaulting to a blank string. 
WARN[0000] The "nunCv" variable is not set. Defaulting to a blank string. 
[+] stop 7/7
 ✔ Container northbridge-orders-serv... Stopped  0.6s ✔ Container northbridge-analytics-s... Stopped  0.5s ✔ Container northbridge-auth-service-1 Stopped  0.7s ✔ Container northbridge-catalog-ser... Stopped 10.5s ✔ Container northbridge-notificatio... Stopped 10.5s ✔ Container northbridge-inventory-s... Stopped  0.6s ✔ Container northbridge-payments-se... Stopped 10.3s[2026-07-12T14:50:42Z] Dropping and recreating northbridge_db...
 pg_terminate_backend 
----------------------
 t
(1 row)

DROP DATABASE
CREATE DATABASE
[2026-07-12T14:50:43Z] Restoring data...
 set_config 
------------
 
(1 row)

 setval 
--------
     11
(1 row)

 setval 
--------
      4
(1 row)

 setval 
--------
      4
(1 row)

 setval 
--------
     11
(1 row)

 setval 
--------
      8
(1 row)

 setval 
--------
      3
(1 row)

[2026-07-12T14:50:43Z] Restore complete.
[2026-07-12T14:50:43Z] Restarting application services...
WARN[0000] The "apr1" variable is not set. Defaulting to a blank string. 
WARN[0000] The "wcNmmRwU" variable is not set. Defaulting to a blank string. 
WARN[0000] The "nunCv" variable is not set. Defaulting to a blank string. 
WARN[0000] The "apr1" variable is not set. Defaulting to a blank string. 
WARN[0000] The "wcNmmRwU" variable is not set. Defaulting to a blank string. 
WARN[0000] The "nunCv" variable is not set. Defaulting to a blank string. 
WARN[0000] The "apr1" variable is not set. Defaulting to a blank string. 
WARN[0000] The "wcNmmRwU" variable is not set. Defaulting to a blank string. 
WARN[0000] The "nunCv" variable is not set. Defaulting to a blank string. 
WARN[0000] The "apr1" variable is not set. Defaulting to a blank string. 
WARN[0000] The "wcNmmRwU" variable is not set. Defaulting to a blank string. 
WARN[0000] The "nunCv" variable is not set. Defaulting to a blank string. 
[+] start 9/9
 ✔ Container northbridge-postgres-1              Healthy                                                                  0.5s ✔ Container northbridge-redis-1                 Healthy                                                                  0.5s ✔ Container northbridge-auth-service-1          Healthy                                                                 31.5s ✔ Container northbridge-analytics-service-1     Started                                                                  1.3s ✔ Container northbridge-catalog-service-1       Healthy                                                                 32.0s ✔ Container northbridge-payments-service-1      Healthy                                                                 32.0s ✔ Container northbridge-notifications-service-1 Healthy                                                                 31.0s ✔ Container northbridge-inventory-service-1     Healthy                                                                 31.9s ✔ Container northbridge-orders-service-1        Started                                                                  0.3s[2026-07-12T14:51:16Z] All services restarted. Restore successful.
[ec2-user@ip-172-31-28-172 northbridge]$ 











