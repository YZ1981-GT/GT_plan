# Implementation Plan

## Overview

修正函证三项覆盖率口径（以 TB population 为分母）、收敛单一真源、移除死端点。
strangler 式加法改动：先建安全网锁基线 → 前端口径 → UI 一致性 → 后端 population 注入 → 移除死端点 → 验证门。
审计口径敏感，测试先行；population 缺失 Skip-on-missing。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1"], "description": "安全网/基线锁定" },
    { "wave": 1, "tasks": ["2", "3"], "description": "前端口径 + types" },
    { "wave": 2, "tasks": ["4"], "description": "UI 一致性 + 接线 population" },
    { "wave": 3, "tasks": ["5", "6"], "description": "后端 population 解析 + 注入 + 单测" },
    { "wave": 4, "tasks": ["7"], "description": "移除死端点 /stats + 清理假绿" },
    { "wave": 5, "tasks": ["8"], "description": "验证门 + 零回归" }
  ]
}
```

## Tasks

- [x] 1. 安全网：锁定当前覆盖率行为基线，核实 /stats 无消费者
  - 运行现有 `useConfirmationData.spec.ts`，记录 `reply_coverage` / `confirmation_coverage` 当前期望值与测试数据（是否全 in-flight）
  - grep 确认 `GET /confirmations/stats` 前端零消费者、后端测试引用点清单
  - _Requirements: 6.1, 6.2_

- [x] 2. 扩展 `ConfirmationCoverageMetrics` 类型
  - `confirmation_coverage: number | null`、新增 `confirmed_coverage: number | null`、`population_available: boolean`，保留 `reply_coverage`/`warn_level`
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 3. 修正 `useConfirmationData.coverageMetrics` 口径 + 单测
  - 入参新增可选 `population: () => number | null`
  - confirmation/confirmed_coverage 以 population 为分母（null 分支）；reply_coverage 改笔数口径 `repliedCount/sentCount`（sentCount 用 `isConfirmationInFlight`）；warn_level 按 Req5
  - 扩展 `useConfirmationData.spec.ts`：Property1-6/9（population=null/0/正、sentCount=0、warn 三分支）；迁移旧 reply_coverage 断言到 sentCount 口径
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.4, 5.1, 5.2, 5.3, 6.2_

- [x] 4. ConfirmationDashboard 口径一致 + GtConfirmationSummary 接线 population
  - Dashboard：回函覆盖率 tooltip 改笔数口径；函证覆盖率 population 缺失显示占位/禁用；新增确认覆盖率行；缺失 warn banner
  - GtConfirmationSummary：`population = htmlData.project_context?.population_amount ?? null` 传入 useConfirmationData；同步公式面板文案（已与口径一致，核对即可）
  - _Requirements: 1.2, 2.3, 5.3_

- [x] 5. 后端 `_resolve_confirmation_population` + `_ACCOUNT_TYPE_TO_CODE_PREFIX` + 单测
  - 新建解析函数（`wp_render_config_helpers` 或 confirmation 渲染同处）：中文科目名→前缀→`get_active_filter`+trial_balance audited SUM（负债 abs）；无匹配/0→None；异常 fail-open None
  - 新建 `test_confirmation_population.py`：Property4/7/8（映射覆盖、无匹配 None、负债 abs、mock TB SUM）
  - _Requirements: 1.4, 3.2, 3.3_

- [x] 6. confirmation-summary 渲染注入 population_amount
  - 渲染路径读已持久化/播种 confirmation-v1 htmlData，含 rows 时解析 population，加法式写入 `project_context.population_amount`（不改 rows/_format/其它字段）
  - _Requirements: 3.1, 3.4_

- [x] 7. 移除死端点 `GET /confirmations/stats` + 清理假绿测试
  - 删除 `confirmation_stats` 路由；删除/改写断言其口径的测试（若无专门测试则确认无残留）
  - _Requirements: 4.1, 4.3, 4.4_

- [x] 8. 验证门 + 零回归
  - get_diagnostics（改动前端/后端文件全清）；Vite transform 200（前端）；AST 编译（后端）
  - 全量：前端 confirmation vitest 绿；后端 confirmation 相关 pytest 绿
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

## Notes

- **边界**：不碰 alternative-* / Hub 投影 / 舞弊信号落库 / 阈值-B15 联动。
- **Skip-on-missing 铁律**：population 缺失 → 覆盖率 null + UI 占位，绝不用 0 或 sum(amounts) 冒充。
- **口径唯一真源**：移除 /stats 后，`coverageMetrics` 为唯一权威；如后续需服务端聚合，另起接 population 实现（不复活死端点口径）。
- **零回归关键**：reply_coverage 从 totalCount→sentCount，若旧测试数据非全 in-flight 需重算期望；不得放宽断言绕过。
