# Phase 8 综合指南（API + 部署 + 用户手册）

> 合并自原 PHASE8_API.md / PHASE8_DEPLOYMENT.md / PHASE8_USER_GUIDE.md

---

## 1. 概述

Phase 8 聚焦性能提升、数据校验、安全增强和用户体验优化。

主要改进：
- 穿透查询游标分页（支持 10 万+ 条虚拟滚动）
- 底稿编辑体验（虚拟滚动、批量预填、离线缓存 Service Worker）
- 报表导出优化（模板缓存 + 异步 PDF + 格式校验）
- 数据校验 API（一致性/完整性自动校验）
- 安全增强（数据加密、登录锁定、审计日志导出）
- 性能监控（Prometheus 指标 + 慢查询检测）

---

## 2. 部署

### 2.1 前置条件

- Python 3.12+ / PostgreSQL 16+ / Redis 6.x+ / Node.js 18+

### 2.2 新增依赖

```bash
# 后端
pip install prometheus-client>=0.19.0 cryptography>=41.0.0

# 前端
cd audit-platform/frontend && npm install vue-virtual-scroller@^2.0.0
```

### 2.3 配置项（.env）

```env
EVENT_DEBOUNCE_MS=500
FORMULA_EXECUTE_TIMEOUT=10
ENCRYPTION_KEY=your-fernet-key-here   # Fernet.generate_key()
REDIS_URL=redis://localhost:6379/0
```

### 2.4 数据库迁移

```bash
python -m alembic upgrade head
```

迁移内容（034）：`trial_balance.currency_code` VARCHAR(3) 默认 'CNY' + 5 个复合索引。

### 2.5 Service Worker

`public/sw.js` 自动注册，Network-first with cache fallback 策略。

### 2.6 回滚

```bash
python -m alembic downgrade -1
```

---

## 3. API 端点

### 3.1 数据校验

| 端点 | 说明 |
|------|------|
| `POST /api/projects/{pid}/data-validation` | 触发校验 |
| `GET /api/projects/{pid}/data-validation/findings` | 查询结果（?severity=&type=） |
| `POST /api/projects/{pid}/data-validation/fix` | 一键修复（body: finding_ids[]） |
| `POST /api/projects/{pid}/data-validation/export` | 导出报告（format: excel） |

### 3.2 性能监控（admin）

| 端点 | 说明 |
|------|------|
| `GET /api/admin/performance-stats` | 概览（avg_response/cache_hit_rate/connections） |
| `GET /api/admin/performance-metrics` | 时序数据（?period=1h/6h/24h/7d） |
| `GET /api/admin/slow-queries` | 慢查询（?threshold_ms=1000&limit=20） |

### 3.3 安全监控

| 端点 | 说明 |
|------|------|
| `GET /api/security/login-attempts` | 登录记录（?username=&status=） |
| `POST /api/security/lock-account` | 锁定账户 |
| `GET /api/security/sessions` | 活跃会话 |
| `GET /api/audit-logs/export` | 导出审计日志（?start_date=&format=csv） |

### 3.4 穿透查询（优化）

`GET /api/projects/{pid}/ledger/penetrate?account_code=&cursor=&limit=100`

游标分页，返回 `{items, next_cursor, has_more}`。

### 3.5 试算表（优化）

`GET /api/projects/{pid}/trial-balance?year=&currency_code=CNY`

---

## 4. 性能告警阈值

| 指标 | warning | critical |
|------|---------|----------|
| API 响应时间 | > 3000ms | > 10000ms |
| DB 查询时间 | > 1000ms | — |
| 缓存命中率 | < 50% | — |

---

## 5. 安全配置

- 加密密钥：`Fernet.generate_key()`
- 登录锁定：5 次失败 → 锁 30 分钟
- JWT：access 30min / refresh 7d

---

## 6. 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+S | 保存 |
| Ctrl+Z / Ctrl+Shift+Z | 撤销/重做 |
| Ctrl+F | 搜索 |
| Ctrl+K | 全局搜索 |
| Ctrl+E | 导出 |
| F5 | 刷新数据 |
| Escape | 关闭弹窗 |
