#!/bin/bash
sudo -u postgres psql -d audit_platform -Atc "SELECT drift_type, count(*) FROM schema_drift_log GROUP BY drift_type ORDER BY 2 DESC" 2>/dev/null
echo "---failures---"
sudo -u postgres psql -d audit_platform -Atc "SELECT count(*) FROM schema_migration_failures"
