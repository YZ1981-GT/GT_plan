# 零停机滚动部署运行手册（A 方案：单机多副本）

## 概述

本文档描述基于 Docker Compose + nginx 反向代理的零停机滚动更新流程。

## 前置条件

- Docker Compose 运行中
- nginx 服务已启动（`docker/nginx/nginx.conf`）
- 至少 2 个后端副本（backend1/backend2）

## 部署步骤

### 1. 构建版本注入

```bash
./scripts/deploy/inject_build_version.sh
```

验证：`cat backend/app/_build_version.json` 确认 `git_commit` 非 "unknown"

### 2. 迁移兼容性检查

```bash
python backend/scripts/check/check_migration_compat.py --mode warning
```

确认无非豁免违规。

### 3. 构建新镜像

```bash
docker compose build backend
```

### 4. 执行滚动更新

```bash
./scripts/deploy/rolling_update.sh <new-image-tag>
```

脚本自动完成：启动新副本 → 轮询 /readyz → nginx reload → 停旧副本

### 5. 验证

```bash
curl http://localhost/api/version    # 确认新版本
curl http://localhost/readyz          # 确认就绪
```

## 回滚步骤

1. 保留上一就绪镜像 tag
2. 执行：`./scripts/deploy/rolling_update.sh <previous-image-tag>`
3. 如需数据库回滚：`python -m app.core.migration_runner rollback_to <target_version>`

## 健康验证清单

| 检查项 | 命令 | 期望 |
|--------|------|------|
| 就绪 | `curl /readyz` | 200 `{"status":"ready"}` |
| 存活 | `curl /livez` | 200 `{"status":"alive"}` |
| 版本 | `curl /api/version` | 返回新 git_commit |
| 健康 | `curl /api/health` | 200 healthy/degraded |
