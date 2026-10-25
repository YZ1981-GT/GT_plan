# 需求：公式推送批 B — Tier A 单公式锚点族

> 前置：`formula-push-all-subjects-rollout`（平台化基础设施 + E1/K1 binding，已完成 Task 7~21）。
> 交叉引用：`formula-push-all-subjects-rollout` design §九（批 B）、ADR-FPA-001（按形态分族）。

## 1. 目标

将渲染期 transient seed 的 18 码 21 条锚点迁移到公式推送引擎，由 `TierAAnchorBinding` 族 binding 承载。迁移后锚点值落库（持久化），不再依赖每次打开页面重算。

## 2. 范围

| # | 需求 | 验收标准 |
|---|------|----------|
| B1 | `TierAAnchorBinding` 族 binding 实现 | 通过 `PushBinding` 协议校验；`load_sources` 只需 `load_tb_audited`；无派生、无附注 |
| B2 | 21 条锚点规则迁移 | 每条规则 `policy=system`，`context.tb=trial_balance_audited`；4 条「审定数」列名改写为等价口径并在证据栏逐条写明依据 |
| B3 | D1/D2 减项码正确性 | `1231-01`/`1231-02` 前缀取数命中子目不吞父行 `1231`；测试同时造父码与子目 |
| B4 | 渲染期 seed 保留 | 未推送过的项目打开页面仍有 transient seed 值 |
| B5 | canary D4 L4 验收 | 规则 / 夹具 / 真 ORM / 真 PG / 端点 / 前端真挂载 |
| B6 | 独占键集合更新 | 生成器重跑后含 Tier A 18 码的独占键；`--check` 通过 |
| B7 | 清册更新 | `formula_push_coverage.json` 新增 18 码 L3 条目 |
| B8 | 每条锚点值与渲染期 seed 逐值相等 | 合成数据 + 真库（D4）对拍 |
| B9 | 底稿预填公式去重 | 推送接管的 `item_id` 在 `prefill_formula_mapping.json` 中标记降级；已推送的项目渲染读持久化值而非 seed |
| B10 | 试算表重算→推送联动 | `TRIAL_BALANCE_UPDATED` 事件触发 18 码推送；不阻塞重算流程 |
| B11 | 预设口径一致守卫 | `wp_formula_eval_service._COLUMN_MAP` 的列名映射 == 推送 `FORMULA_CONTEXTS` 的列名映射 |

## 3. 不做

- 审定表组合行 / 性质行 / FS 核对区（归批 C）
- 附注章节推送（归批 E）
- 损益类科目发生额口径（归批 D，但 4 条「审定数」锚点需在本批决定口径）

## 4. 科目清单（现读确认）

实施前从 `d_cycle_extraction_presets.json` + `formula_eval_service` 现扫 21 条锚点，逐条确认 `wp_code`、`item_id`、`expression`、`column_name`，结论写进 tasks 证据栏。
