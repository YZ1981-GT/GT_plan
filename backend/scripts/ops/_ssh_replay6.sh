#!/bin/bash
# 4 张表的 snapshot_id 类型现状
sudo -u postgres psql -d audit_platform -c "SELECT table_name, data_type FROM information_schema.columns WHERE column_name='snapshot_id' AND table_name IN ('export_jobs_v2','export_job_items_v2','export_job_attempts','word_export_task_versions')"
