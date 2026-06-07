# 设计文档：平台治理、维护账本与工程卡点

## 概述

本 spec 解决企业级平台上线后的维护便利性问题。当前平台模块数量大、增长快、文档多、旧新双轨并存，必须建立自动化账本和工程卡点，避免后续维护依赖个人记忆。

## 核心设计

### 1. 四本账

| 账本 | 文件 | 内容 |
|---|---|---|
| API 契约账 | `docs/reference/api-contract-ledger.md` | 路由、权限、错误码、前端路径 |
| 组件账 | `docs/frontend/component-ledger.md` | 全局组件、场景、禁用项、迁移计划 |
| 数据口径账 | `docs/reference/data-semantics-ledger.md` | 金额、年度、准则、状态、stale、来源 |
| 质量账 | `docs/operations/quality-ledger.md` | 测试、PBT、压测、线上缺陷、回归范围 |

账本尽量由脚本生成或半自动更新。

### 2. 自动规模快照

新增 `backend/scripts/analyze/snapshot_scale.py`：

- routers 数
- services 数
- models 数
- migrations 数
- tests 数
- frontend views 数
- components 数
- composables 数

写入 `docs/architecture/service-dependency.md` 或新增 `docs/architecture/scale-snapshot.md` 的标记区块。

### 3. PR 卡点

新增 PR checklist 模板或检查脚本：

- 页面是否使用全局组件
- 金额是否 Decimal
- 状态是否进字典
- 路由是否配权限
- AI 是否需确认
- 穿透是否使用 LinkageContract
- 数据库是否三层一致

### 4. 超大文件治理

新增 `check_hotspot_files` 扩展：

- Vue 文件行数 baseline
- Python service 行数 baseline
- composable 数量 baseline
- 同族模块注册表

重点跟踪：

- `LedgerPenetration.vue`
- `DisclosureEditor.vue`
- `TrialBalance.vue`
- `ReportView.vue`
- 公式引擎族
- 自动保存/编辑锁/表格 composable 族

### 5. SQL 列契约

新增 `check_sql_column_contract.py`：

- 扫描 `select(Model.col)`
- 扫描裸 SQL 中 `alias.column`
- 对比 ORM mapped columns
- 对比 migration DDL

目标是防止“引用不存在列”导致线上 500。

### 6. 运维 smoke

上线检查覆盖：

- `/api/health`
- `/wopi/health`
- OnlyOffice `/healthcheck`
- Redis ping
- Postgres migration status
- Worker 状态
- SSE 连接
- Schema drift
- degraded 状态

## 不在范围

- 不重构业务模块。
- 不替代需求/设计文档。
- 不强制所有历史文档一次性归档。

## 现有代码锚点

- `backend/scripts/check/check_hotspot_files.py`
- `backend/scripts/check/check_router_registration.py`
- `backend/scripts/check/check_migrations.py`
- `backend/scripts/check/check_no_float_amount.py`
- `backend/scripts/check/check_property_coverage.py`
- `backend/scripts/check/check_routes.py`
- `.github/workflows/ci.yml`
- `.git-hooks/pre-commit`
- `docs/frontend/component-usage.md`
- `docs/reference/frontend-backend-alignment.md`
- `docs/deployment/smoke-test-checklist.md`

## 脚本输出草案

### `snapshot_scale.py`

```json
{
  "backend": {
    "routers": 303,
    "services": 453,
    "models": 68,
    "migrations": 59,
    "tests": 682
  },
  "frontend": {
    "views": 113,
    "components": 437,
    "composables": 187
  }
}
```

### `check_sql_column_contract.py`

扫描范围：

- SQLAlchemy ORM `Model.column`
- `select(Model.column)`
- 裸 SQL `alias.column`
- migration DDL 列集合
- ORM mapped columns

### PR checklist 草案

- 是否新增页面，使用了哪些全局组件？
- 是否新增金额字段，Decimal 如何序列化？
- 是否新增状态，是否进入枚举字典？
- 是否新增 API，权限和错误码是什么？
- 是否新增 AI 输出，是否有人工确认？
- 是否新增穿透，是否使用 LinkageContract？

## 迁移策略

1. P0 只新增账本和检查，不 fail 历史债务。
2. 对历史问题建立 baseline。
3. CI 只 fail 新增违规。
4. 每月降低 baseline，逐步还债。

## 风险与回滚

- 风险：CI 一次性过严阻塞开发。  
  回滚：新增检查先 warning，两周后切 fail。
- 风险：账本无人维护。  
  回滚：尽量脚本生成，手工字段最小化。
