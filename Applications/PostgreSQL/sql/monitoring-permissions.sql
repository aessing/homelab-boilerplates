-- Run once on the writable primary after CNPG creates its exporter role.
-- The bootstrap hardening revokes PUBLIC CONNECT on these two databases.
-- Do not grant superuser, application-table access or additional memberships.
BEGIN;
GRANT CONNECT ON DATABASE postgres, initdb TO cnpg_metrics_exporter;
COMMIT;
