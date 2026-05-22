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

### 迁移脚本

Phase 8 包含 1 个迁移脚本：

```bash
# 执行迁移
python -m alembic upgrade head

# 或指定版本
python -m alembic upgrade 034
```

**迁移内容（034_phase8_currency_and_indexes.py）：**
- `trial_balance` 表添加 `currency_code` 字段（VARCHAR(3)，默认 'CNY'）
- 创建 `idx_trial_balance_currency_code` 索引
- 创建 `idx_trial_balance_project_year_std_code` 复合索引
- 创建 `idx_tb_balance_project_year_deleted` 复合索引
- 创建 `idx_adjustments_project_year_account_code` 复合索引
- 创建 `idx_import_batches_project_year` 复合索引

### 回滚

```bash
python -m alembic downgrade -1
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

- [ ] 数据库迁移成功（`alembic current` 显示 034）
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

1. 数据库回滚：`python -m alembic downgrade -1`
2. 后端回滚：切换到 Phase 7 分支/版本
3. 前端回滚：部署 Phase 7 构建产物
4. 配置回滚：移除新增环境变量

**注意：** 回滚后 `currency_code` 字段和复合索引将被删除，不影响现有数据。
