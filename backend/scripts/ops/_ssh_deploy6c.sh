#!/bin/bash
# 查 DB 已应用到的最高版本号
sudo -u postgres psql -d audit_platform -Atc "SELECT MAX(version::int) FROM schema_version WHERE version ~ '^[0-9]+$'"
echo "--- V190~V208 哪些已应用 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT version FROM schema_version WHERE version::int >= 190 ORDER BY version::int" | tr '\n' ' '
echo
