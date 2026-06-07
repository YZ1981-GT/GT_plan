# 依赖组件恢复步骤

> 记录 Postgres、Redis、文件存储、OnlyOffice 四大依赖的故障恢复标准操作流程。
> 配合 `backup-drill-record-template.md` 使用，每次演练按此步骤执行。

## 目录

1. [Postgres 数据库恢复](#1-postgres-数据库恢复)
2. [Redis 缓存恢复](#2-redis-缓存恢复)
3. [文件存储恢复](#3-文件存储恢复)
4. [OnlyOffice 依赖恢复](#4-onlyoffice-依赖恢复)
5. [全量灾难恢复流程](#5-全量灾难恢复流程)

---

## 1. Postgres 数据库恢复

### 1.1 前置条件

- 备份文件可访问（pg_dump 文件或 WAL 归档）
- 目标服务器 Postgres 16 已安装
- 有足够磁盘空间（备份文件大小 × 3）

### 1.2 恢复方式一：pg_dump 逻辑恢复

适用场景：单库恢复、跨版本迁移、部分表恢复。

```bash
# 1. 停止应用服务（防止新写入）
docker compose stop backend worker

# 2. 验证备份文件完整性
pg_restore --list backup_audit_platform_YYYYMMDD.dump | head -20

# 3. 创建新数据库（或清空目标库）
psql -U postgres -c "CREATE DATABASE audit_platform_restore;"

# 4. 恢复数据
pg_restore \
  --dbname=audit_platform_restore \
  --username=postgres \
  --no-owner \
  --no-privileges \
  --jobs=4 \
  backup_audit_platform_YYYYMMDD.dump

# 5. 验证恢复结果
psql -U postgres -d audit_platform_restore -c "
  SELECT schemaname, tablename, n_live_tup
  FROM pg_stat_user_tables
  ORDER BY n_live_tup DESC
  LIMIT 20;
"

# 6. 切换数据库（重命名）
psql -U postgres -c "ALTER DATABASE audit_platform RENAME TO audit_platform_old;"
psql -U postgres -c "ALTER DATABASE audit_platform_restore RENAME TO audit_platform;"

# 7. 运行待执行迁移（如有）
cd backend
python -c "
import asyncio
from app.core.migration_runner import MigrationRunner
asyncio.run(MigrationRunner().run_pending())
"

# 8. 重启应用服务
docker compose start backend worker
```

### 1.3 恢复方式二：WAL 点恢复（PITR）

适用场景：恢复到指定时间点、误操作回退。

```bash
# 1. 停止 Postgres
systemctl stop postgresql

# 2. 清空数据目录（保留 pg_wal）
rm -rf /var/lib/postgresql/16/main/*

# 3. 恢复 base backup
pg_basebackup 文件解压到数据目录

# 4. 配置 recovery.conf / postgresql.conf
cat >> /var/lib/postgresql/16/main/postgresql.conf << EOF
restore_command = 'cp /backup/wal/%f %p'
recovery_target_time = '2026-06-15 14:30:00+08'
recovery_target_action = 'promote'
EOF

# 5. 创建恢复信号文件
touch /var/lib/postgresql/16/main/recovery.signal

# 6. 启动 Postgres（自动恢复到指定时间）
systemctl start postgresql

# 7. 验证恢复时间点
psql -U postgres -d audit_platform -c "SELECT now(), pg_last_xact_replay_timestamp();"
```

### 1.4 恢复后验证

```bash
# 核心验证脚本
psql -U postgres -d audit_platform -c "
  -- 检查迁移版本
  SELECT MAX(version) as latest_migration FROM schema_migrations;

  -- 检查关键表非空
  SELECT 'projects' as tbl, count(*) FROM projects
  UNION ALL SELECT 'users', count(*) FROM users
  UNION ALL SELECT 'working_paper', count(*) FROM working_paper
  UNION ALL SELECT 'trial_balance', count(*) FROM trial_balance;

  -- 检查无损坏索引
  SELECT indexrelname, idx_scan FROM pg_stat_user_indexes WHERE idx_scan = 0 LIMIT 10;
"
```

---

## 2. Redis 缓存恢复

### 2.1 前置条件

- Redis 6.x / 7.x 已安装
- RDB 或 AOF 备份文件可访问
- 足够内存（当前数据量 × 1.5）

### 2.2 RDB 恢复

```bash
# 1. 停止 Redis
docker compose stop audit-redis

# 2. 备份当前数据（以防需要回退）
cp /data/redis/dump.rdb /data/redis/dump.rdb.bak

# 3. 替换为备份文件
cp /backup/redis/dump_YYYYMMDD.rdb /data/redis/dump.rdb

# 4. 启动 Redis
docker compose start audit-redis

# 5. 验证
redis-cli -p 6379 ping
redis-cli -p 6379 dbsize
redis-cli -p 6379 info memory | grep used_memory_human
```

### 2.3 AOF 恢复

```bash
# 1. 停止 Redis
docker compose stop audit-redis

# 2. 检查 AOF 文件完整性
redis-check-aof --fix /backup/redis/appendonly.aof

# 3. 替换 AOF 文件
cp /backup/redis/appendonly.aof /data/redis/appendonly.aof

# 4. 确保 redis.conf 启用 AOF
# appendonly yes

# 5. 启动 Redis
docker compose start audit-redis
```

### 2.4 Redis 完全丢失（冷启动）

Redis 作为缓存层，完全丢失时应用不崩溃但性能下降：

```bash
# 1. 启动空 Redis
docker compose start audit-redis

# 2. 应用自动重建缓存（session 需重新登录）
# - 用户 session：需重新登录
# - 编辑锁：自动过期重建
# - 查询缓存：自动回源 DB

# 3. 通知用户重新登录
echo "Redis 缓存已重建，用户需重新登录"
```

### 2.5 恢复后验证

```bash
redis-cli -p 6379 << 'EOF'
PING
DBSIZE
INFO keyspace
INFO memory
EOF
```

---

## 3. 文件存储恢复

### 3.1 前置条件

- 文件备份可访问（rsync 镜像 / 对象存储快照）
- 目标目录有足够空间
- 应用配置的 `UPLOAD_DIR` 路径正确

### 3.2 本地文件系统恢复

```bash
# 1. 确认备份源（示例路径，按实际部署调整）
BACKUP_SOURCE="/backup/uploads/YYYYMMDD/"
TARGET_DIR="/data/uploads/"

# 2. 停止应用（防止写冲突）
docker compose stop backend worker

# 3. 恢复文件
rsync -avz --delete "$BACKUP_SOURCE" "$TARGET_DIR"

# 4. 修复权限
chown -R 1000:1000 "$TARGET_DIR"
chmod -R 755 "$TARGET_DIR"

# 5. 验证文件数量
echo "备份文件数: $(find $BACKUP_SOURCE -type f | wc -l)"
echo "恢复文件数: $(find $TARGET_DIR -type f | wc -l)"

# 6. 启动应用
docker compose start backend worker
```

### 3.3 恢复后验证

```bash
# 验证关键路径存在
ls -la /data/uploads/projects/
ls -la /data/uploads/knowledge/
ls -la /data/uploads/exports/

# 通过 API 验证文件可访问
curl -s -o /dev/null -w "%{http_code}" http://localhost:9980/api/health
```

---

## 4. OnlyOffice 依赖恢复

### 4.1 前置条件

- Docker 可用
- OnlyOffice Document Server 镜像可拉取
- WOPI 回调地址可达

### 4.2 重新部署

```bash
# 1. 停止旧容器（如存在）
docker stop onlyoffice-documentserver || true
docker rm onlyoffice-documentserver || true

# 2. 拉取镜像
docker pull onlyoffice/documentserver:latest

# 3. 启动（带持久化卷和配置）
docker run -d \
  --name onlyoffice-documentserver \
  --restart=always \
  -p 8080:80 \
  -v /data/onlyoffice/data:/var/www/onlyoffice/Data \
  -v /data/onlyoffice/log:/var/log/onlyoffice \
  -v /data/onlyoffice/fonts:/usr/share/fonts/custom \
  -e JWT_ENABLED=true \
  -e JWT_SECRET=<your-jwt-secret> \
  onlyoffice/documentserver

# 4. 等待就绪
sleep 30
curl -s http://localhost:8080/healthcheck
```

### 4.3 配置恢复

```bash
# 恢复自定义配置（如有）
docker cp /backup/onlyoffice/local.json \
  onlyoffice-documentserver:/etc/onlyoffice/documentserver/local.json

# 恢复字体（如有自定义字体）
docker cp /backup/onlyoffice/fonts/ \
  onlyoffice-documentserver:/usr/share/fonts/custom/

# 重启使配置生效
docker restart onlyoffice-documentserver
```

### 4.4 恢复后验证

```bash
# 健康检查
curl -s http://localhost:8080/healthcheck
# 预期返回: true

# WOPI discovery（验证回调配置）
curl -s http://localhost:8080/hosting/discovery | head -20

# 应用端验证
curl -s http://localhost:9980/wopi/health
# 预期返回 200 + "healthy"
```

---

## 5. 全量灾难恢复流程

当所有组件需要从零恢复时的标准流程：

### 执行顺序

```
1. 基础设施 → 2. 数据层 → 3. 缓存层 → 4. 文件层 → 5. 应用层 → 6. 依赖服务
```

### 详细步骤

| 顺序 | 组件 | 操作 | 依赖 | 预计耗时 |
|------|------|------|------|----------|
| 1 | Docker / OS | 安装基础环境 | 无 | 30min |
| 2 | Postgres | 恢复数据库（见 §1） | Docker | 15-60min |
| 3 | Redis | 恢复缓存或冷启动（见 §2） | Docker | 5min |
| 4 | 文件存储 | 恢复底稿/附件（见 §3） | 磁盘 | 15-120min |
| 5 | 应用服务 | 部署 backend + frontend | PG + Redis + 文件 | 10min |
| 6 | OnlyOffice | 部署文档服务（见 §4） | Docker + 应用 | 10min |
| 7 | 验证 | smoke checklist 全量检查 | 全部 | 15min |

### 恢复完成验证

参照 `docs/deployment/platform-smoke-checklist.md` 执行全量检查。

---

## 附录：备份策略建议

| 组件 | 备份方式 | 频率 | 保留期 | 存储位置 |
|------|----------|------|--------|----------|
| Postgres | pg_dump (full) | 每日 02:00 | 30 天 | 异地存储 |
| Postgres | WAL 归档 | 持续 | 7 天 | 本地 + 异地 |
| Redis | RDB snapshot | 每小时 | 7 天 | 本地 |
| 文件存储 | rsync 增量 | 每日 03:00 | 30 天 | 异地存储 |
| OnlyOffice 配置 | 配置文件复制 | 变更后 | 永久 | Git |
| 应用配置 | .env + docker-compose | 变更后 | 永久 | Git (加密) |

## 变更历史

| 日期 | 版本 | 变更内容 | 操作人 |
|------|------|----------|--------|
| 2026-06-07 | v1.0 | 初始版本 | 系统 |
