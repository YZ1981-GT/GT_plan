# 平台全局改进 Spec 总路线图

> 本路线图协调 6 个平台级 spec 的执行顺序、依赖关系与 P0-MVP 范围。  
> 适用范围：`platform-*` 六个新 spec。  
> 原则：先治理卡点，再打上下文地基，再接数据联动，最后做角色化作业台。

## 1. Spec 清单

| Spec | 定位 | 推荐阶段 |
|---|---|---|
| `platform-maintenance-governance` | 工程治理、账本、CI 卡点、smoke | 最先启动 |
| `platform-context-permission-foundation` | 项目上下文、年度、权限矩阵、字典 | 第一批 |
| `platform-linkage-contract-stale` | 数据联动契约、穿透、stale、签发检查 | 第一批 |
| `platform-ui-editing-consistency` | 页面骨架、金额、编辑状态、表格一致性 | 第一批并行 |
| `platform-evidence-knowledge-ai-governance` | 附件证据、AI 确认、知识库、交付件 | 第二批 |
| `platform-role-workbench-quality-loop` | 五角色作业台、质量闭环、签发雷达 | 第三批 |

## 2. 依赖图

```text
platform-maintenance-governance
  ├─ platform-context-permission-foundation
  │    ├─ platform-linkage-contract-stale
  │    │    ├─ platform-evidence-knowledge-ai-governance
  │    │    └─ platform-role-workbench-quality-loop
  │    └─ platform-ui-editing-consistency
  └─ 所有 spec 的 CI / 账本 / smoke 卡点
```

## 3. 推荐执行顺序

### 第一阶段：治理与地基

1. `platform-maintenance-governance` P0-MVP
2. `platform-context-permission-foundation` P0-MVP
3. `platform-linkage-contract-stale` P0-MVP
4. `platform-ui-editing-consistency` P0-MVP

目标：不再继续制造不可维护债务；项目、年度、权限、金额、错误、stale、穿透有最小统一口径。

### 第二阶段：证据与 AI

1. `platform-evidence-knowledge-ai-governance` P0-MVP
2. `platform-linkage-contract-stale` P1
3. `platform-ui-editing-consistency` P1

目标：附件、AI、复核证据、交付件逐步进入统一证据链。

### 第三阶段：五角色工作台

1. `platform-role-workbench-quality-loop` P1
2. `platform-evidence-knowledge-ai-governance` P1/P2
3. `platform-maintenance-governance` P1/P2

目标：把底层治理成果呈现给助理、经理、质控、合伙人、EQCR。

## 4. P0-MVP 总清单

- [ ] 规模快照脚本可运行，输出稳定。
- [ ] SQL 列契约可 report 不存在列。
- [ ] PR checklist 包含全局组件、Decimal、枚举、权限、AI、LinkageContract。
- [ ] ProjectContext facade 可提供 project/year/status/role。
- [ ] 年度切换能清理核心缓存。
- [ ] 权限矩阵首批 operation code 可前后端共用。
- [ ] LinkageContract schema 前后端一致。
- [ ] wp_code 可解析到 wp_id 并跳转底稿。
- [ ] stale 静默吞错改为 degraded 记录。
- [ ] 金额展示/复制/解析不改变 Decimal 值。
- [ ] API 错误统一进入 `handleApiError`。
- [ ] 编辑状态机在至少 1 个核心编辑页跑通。
- [ ] AI draft/confirmed/rejected 状态映射完成。
- [ ] 附件影响范围查询至少覆盖已知引用。

## 5. 并行建议

- `platform-maintenance-governance` 可独立先做。
- `platform-ui-editing-consistency` 的金额/错误处理可与 `platform-context-permission-foundation` 并行。
- `platform-role-workbench-quality-loop` 不建议早于 Context / Linkage / Evidence P0。
- 所有涉及 DB 的任务必须遵守：migration + ORM + schema + service + 契约测试。

## 6. 统一验收口径

每个 spec 至少需要：

- P0-MVP 可演示。
- pytest / Vitest 对应契约测试。
- UAT 场景至少 1 条主路径。
- CI 新增检查先 warning，稳定后 fail。
- 文档账本可追溯对应 API、组件、数据口径和测试。
