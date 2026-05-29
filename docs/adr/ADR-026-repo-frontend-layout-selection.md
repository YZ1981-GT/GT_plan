# ADR-026: 仓库前端 layout 选型

- **Date**: 2026-05-29
- **Status**: Accepted
- **Spec**: repo-frontend-layout-unification

## Context

仓库历史上同时存在两个前端目录：

- `frontend/`（仓库根）：5 个 .vue 文件（`custom-query/2 + eqcr/3`）/ 0 个 .ts → 空壳
- `audit-platform/frontend/`：498 .vue / 379 .ts → 真前端

每次 grep / IDE 跳转 / CI 配置 / 新人接手都受双路径影响，memory.md 一度记录"判断前端模块存在性必须同时检查"作为兜底铁律。

## Decision

**采用方案 A**：保留 `audit-platform/frontend/` 为唯一前端路径，删除仓库根 `frontend/` 目录。

5 空壳组件经引用扫描发现**全部 0 引用**（C 类死代码），直接 `git rm`。

## Alternatives Considered

### 方案 B：把 `audit-platform/frontend/` 提到根

- **优点**：仓库根扁平 `frontend/` + `backend/`
- **缺点**：120+ 处硬编码改动（vite / Storybook / Playwright config / package.json / start-dev.bat / README / CI），高风险
- **拒绝理由**：ROI 远低于方案 A（5 文件 vs 120 处）+ 风险高 + 改动量大

### 方案 C：保留双路径继续兜底

- **优点**：0 改动
- **缺点**：grep 噪音 + 新人困惑 + IDE 智能提示混乱 + memory 兜底铁律永远留着
- **拒绝理由**：每次操作都被影响，长期成本高

## Consequences

### 正面

- 仓库前端单一来源：`audit-platform/frontend/`
- grep `<ComponentName>` 只命中真路径
- IDE 跳转无歧义
- pre-commit hook `check-no-root-frontend` 防止回归
- memory.md 删除"双路径兜底"铁律 → 减一条心智负担

### 负面（低风险）

- git history 中 `frontend/src/components/{custom-query,eqcr}/` 5 个文件被删（git tag `pre-frontend-cleanup-2026-05-29` 可回退）

## Verification

- 引用扫描脚本 `_verify_orphan_frontend_components.py` 确认 5 文件 0 引用
- backend `from app.main import app` smoke 通过
- spec 测试集 96/96 全绿（前端无连带破坏）
- 全仓 grep `frontend/src/` 排除 `audit-platform/` 后 0 业务匹配（仅文档历史档案）
