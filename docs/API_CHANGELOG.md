# API 端点变更日志

记录每个版本的新增/删除/修改端点，便于前后端协同和版本追溯。

## 格式规范

```
### vX.Y.Z (YYYY-MM-DD)

#### 新增
- `METHOD /api/path` — 简要说明

#### 修改
- `METHOD /api/path` — 变更内容（参数/返回值/行为）

#### 废弃
- `METHOD /api/path` — 废弃原因，替代方案

#### 删除
- `METHOD /api/path` — 删除原因
```

---

## R6 (2026-05-07)

### 新增
- `GET /api/qc/rules` — 质控规则列表（支持分页/筛选）
- `GET /api/qc/rules/{id}` — 质控规则详情
- `PATCH /api/qc/rules/{id}` — 更新质控规则
- `POST /api/qc/rules/{id}/dry-run` — 规则试运行
- `POST /api/qc/inspections` — 创建抽查批次
- `GET /api/qc/inspections` — 抽查批次列表
- `GET /api/qc/inspections/{id}` — 抽查批次详情
- `POST /api/qc/inspections/{id}/items/{itemId}/verdict` — 录入质控结论
- `POST /api/qc/inspections/{id}/report` — 生成质控报告
- `GET /api/qc/cases` — 案例库列表
- `GET /api/qc/cases/{id}` — 案例详情
- `POST /api/qc/annual-reports` — 触发年报生成
- `GET /api/qc/annual-reports` — 年报列表
- `GET /api/qc/annual-reports/{id}/download` — 下载年报
- `GET /api/qc/audit-log-compliance/findings` — 日志合规命中列表
- `POST /api/qc/audit-log-compliance/run` — 手动触发合规检查
- `PATCH /api/qc/audit-log-compliance/findings/{id}/status` — 更新审查状态
- `GET /api/qc/archive-readiness` — 归档就绪检查

### 废弃
- `GET /api/projects/{pid}/pbc` — stub 实现，R7+ 计划
- `GET /api/projects/{pid}/confirmations` — stub 实现，R7+ 计划

## R5 (2026-05-06)

### 新增
- `GET /api/eqcr/workbench` — EQCR 工作台项目列表
- `GET /api/eqcr/projects/{pid}/overview` — EQCR 项目概览
- `POST /api/eqcr/opinions` — 创建 EQCR 意见
- `PATCH /api/eqcr/opinions/{id}` — 更新 EQCR 意见
- `GET /api/eqcr/independence/annual/check` — 年度独立性声明检查
- `POST /api/eqcr/independence/annual/submit` — 提交年度声明
- `GET /api/eqcr/metrics` — EQCR 指标看板
- 完整 38 端点见 `backend/app/routers/eqcr/__init__.py`

## R4 (2026-05-06)

### 新增
- `POST /api/projects/{pid}/ledger/penetrate-by-amount` — 按金额穿透
- `GET /api/projects/{pid}/working-papers/{wpId}/editing-lock` — 编辑锁状态
- `POST /api/projects/{pid}/working-papers/{wpId}/editing-lock/acquire` — 获取编辑锁
- `DELETE /api/projects/{pid}/working-papers/{wpId}/editing-lock` — 释放编辑锁
