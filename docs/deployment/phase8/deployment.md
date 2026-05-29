# Phase 8 部署文档

## 概述

Phase 8 部署涉及数据库迁移、后端服务更新、前端构建和配置变更。

---

## 1. 前置条件

- Python 3.12+
- PostgreSQL 16+
- Redis 6.x+
- Node.js 18+

## 2. 数据库迁移

### 迁移系统（D6 版本化 SQL 脚本）

项目使用自研 D6 迁移系统（`backend/migrations/V*.sql` + `R*.sql`），后端启动时由
`MigrationRunner` 自动检测并应用未执行的版本（per-migration 异常隔离 + 失败追踪）。

Phase 8 历史曾有 alembic 迁移 `034_phase8_currency_and_indexes.py`，已合并到 D6
体系。当前部署仅需启动后端即触发自动迁移，**无需**手动执行命令。

```bash
# 启动后端会自动跑 backend/migrations/V*.sql 中所有未应用的版本
start-dev.bat   # 开发
uvicorn app.main:app --host 0.0.0.0 --port 9980 --workers 10   # 生产

# 手动诊断（可选）：
python -m app.core.migration_runner
```

**Phase 8 涉及的 schema 变更（已收敛进 V*.sql）：**
- `trial_balance` 表添加 `currency_code` 字段（VARCHAR(3)，默认 'CNY'）
- 创建 `idx_trial_balance_currency_code` 索引
- 创建 `idx_trial_balance_project_year_std_code` 复合索引
- 创建 `idx_tb_balance_project_year_deleted` 复合索引
- 创建 `idx_adjustments_project_year_account_code` 复合索引
- 创建 `idx_import_batches_project_year` 复合索引

### 回滚

执行对应版本的 R*.sql 回滚脚本（手动）：

```bash
# 例：回滚 V034
psql -U postgres -d audit_platform -f backend/migrations/R034__rollback.sql
# 同时清除 schema_version 表对应记录
psql -U postgres -d audit_platform -c "DELETE FROM schema_version WHERE version='034';"
```

---

## 3. 后端部署

### 新增依赖

```bash
pip install prometheus-client>=0.19.0
pip install cryptography>=41.0.0
```

### 配置项

在 `.env` 或环境变量中添加：

```env
# 事件去重窗口（毫秒）
EVENT_DEBOUNCE_MS=500

# 公式执行超时（秒）
FORMULA_EXECUTE_TIMEOUT=10

# 数据加密密钥（Fernet key）
ENCRYPTION_KEY=your-fernet-key-here

# Redis 配置（已有，确认存在）
REDIS_URL=redis://localhost:6379/0
```

### 启动服务

```bash
# 开发环境
start-dev.bat

# 生产环境
uvicorn app.main:app --host 0.0.0.0 --port 9980 --workers 10
```

---

## 4. 前端部署

### 新增依赖

```bash
cd audit-platform/frontend
npm install vue-virtual-scroller@^2.0.0
```

### 构建

```bash
npm run build
```

### Service Worker

Phase 8 新增了 Service Worker 支持离线缓存：
- 文件位置：`public/sw.js`
- 自动注册：在 `main.ts` 中调用 `registerServiceWorker()`
- 缓存策略：Network-first with cache fallback

---

## 5. 性能监控配置

### Prometheus 指标

后端自动暴露 `/metrics` 端点，配置 Prometheus 抓取：

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'audit-platform'
    static_configs:
      - targets: ['localhost:9980']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### 性能阈值告警

| 指标 | 阈值 | 告警级别 |
|------|------|---------|
| API 响应时间 | > 3000ms | warning |
| 数据库查询时间 | > 1000ms | warning |
| 缓存命中率 | < 50% | info |
| API 响应时间 | > 10000ms | critical |

---

## 6. 安全配置

### 加密密钥生成

```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(key.decode())
```

### 登录失败锁定

- 最大失败次数：5 次
- 锁定时长：30 分钟
- 配置位置：`SecurityMonitor` 类常量

---

## 7. 验证清单

部署后执行以下验证：

- [ ] 数据库迁移成功（`/api/health` JSON 中 `migration.applied_count` 含 V034 + 无 failures）
- [ ] `trial_balance.currency_code` 字段存在且默认值为 'CNY'
- [ ] 4 个复合索引已创建（`\di` 查看）
- [ ] Redis 连接正常
- [ ] `/metrics` 端点返回 Prometheus 指标
- [ ] 穿透查询支持 cursor 参数
- [ ] EventBus debounce 机制生效
- [ ] FormulaEngine 超时控制生效（10s）
- [ ] 前端 Service Worker 注册成功

---

## 8. 回滚方案

如需回滚 Phase 8：

1. 数据库回滚：执行 `backend/migrations/R034__rollback.sql` + 清除 schema_version 记录
2. 后端回滚：切换到 Phase 7 分支/版本
3. 前端回滚：部署 Phase 7 构建产物
4. 配置回滚：移除新增环境变量

**注意：** 回滚后 `currency_code` 字段和复合索引将被删除，不影响现有数据。
