# 文档索引

按用途分类，统一查阅入口。新增文档前请先确认归属类别。

## 目录

| 子目录 | 用途 | 适合场景 |
|--------|------|---------|
| [`adr/`](adr/) | 架构决策记录（ADR） | 查"为什么这样设计/取舍"，附备选方案 |
| [`architecture/`](architecture/) | 系统架构与模块设计 | 查"账表导入怎么跑/穿透链路/服务依赖" |
| [`deployment/`](deployment/) | 部署与运维手册 | 部署、灰度、迁移、冒烟测试、K8s 探针 |
| [`reference/`](reference/) | 参考手册（变更日志/配置/对齐清单） | 日常查表（端点变更、配置项、字段对齐） |
| [`frontend/`](frontend/) | 前端专项 | 组件选型、CSS、加载状态、底稿右栏 |
| [`operations/`](operations/) | 运维剧本 | 健康度监控、降级响应 |
| [`proposals/`](proposals/) | 设计建议书（含历史版本） | 全局打磨、新模块规划、深度评估 |
| [`templates/`](templates/) | 文档/代码模板 | 新建 API 端点、新建 spec 时复制 |

## 顶层文件

- `requirements.md` — 系统需求文档（v11，2026-04 修订）

## 文档清单

### adr/ — 架构决策（6）

- `ADR-001-auxiliary-dimension-redundant-storage.md`
- `ADR-002-ledger-view-refactor.md`
- `ADR-003-ledger-import-recovery-playbook.md`
- `ADR-004-ledger-activate-isolation.md`
- `ADR-005-async-activate.md`
- `ADR-006-sse-vs-polling-import-progress.md`

### architecture/ — 架构设计（4）

- `ledger-import-v2.md` — 账表导入 v2 引擎架构（含可见性/下游绑定）
- `service-dependency.md` — 后端服务依赖图（自动生成 by `scripts/gen_service_deps.py`）
- `global-linkage-proposal.md` — 全局联动架构改进方案（Unified Linkage Bus）
- `penetration-map.md` — 穿透闭环路径

### deployment/ — 部署运维（5 + phase8 子目录）

- `mineru.md` — MinerU OCR 服务部署
- `kubernetes-probes.md` — K8s liveness/readiness 探针
- `f-cycle-notes.md` — F 采购存货循环部署注意事项
- `tenant-id-migration.md` — tenant_id 渐进迁移计划
- `smoke-test-checklist.md` — 发版前冒烟清单
- `phase8/` — Phase 8 三件套（`guide.md` 综合 / `api-reference.md` 端点 / `deployment.md` 部署 / `user-guide.md` 用户）

### reference/ — 参考手册（4）

- `api-changelog.md` — API 端点变更日志
- `configuration.md` — 配置中心（.env / config.py / 前端 env）
- `frontend-backend-alignment.md` — 关键端点前后端对齐清单
- `explain-analyze-view.md` — 账表四表查询 EXPLAIN 改造前后对比

### frontend/ — 前端专项（4）

- `component-usage.md` — 组件选型决策树（GtTableExtended / GtFormTable / GtEditableTable）
- `workpaper-side-panel.md` — 底稿右栏 10 Tab 使用指南
- `css-variable-audit.md` — CSS 变量覆盖率审计
- `loading-pattern.md` — 加载状态规范

### operations/ — 运维剧本（1）

- `event-cascade-health.md` — 事件级联健康度运维指南

### proposals/ — 设计建议书（6）

- `platform-global-2026-05-21.md` — 平台全局建议书（5 角色视角）
- `workpaper-development-v2.md` — 审计底稿系统深度开发方案（重构版）
- `ledger-import-priority.md` — 账表导入智能优先落地实施方案
- `refinement-v1.md` — 全局打磨建议 v1（35 项路线图）
- `refinement-v2.md` — 全局打磨建议 v2（角色穿刺）
- `refinement-v3.md` — 全局打磨建议 v3（实测驱动）

### templates/ — 模板（1）

- `NEW_API_ENDPOINT.md` — 新建 API 端点 checklist

## 维护规约

- 新增文档放对应子目录，不要平铺到 `docs/` 根
- 文件名：英文小写 + 连字符（如 `event-cascade-health.md`），保持同目录风格一致
- 文档头部加"用途+受众+最后更新"三件套
- 重大文档变更后同步更新本索引
