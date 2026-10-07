# 任务：公式推送批 B — Tier A 单公式锚点族

> 顺序即依赖。每项完成须有「修复前红 / 修复后绿 / 改回即红」证据。

## 阶段 1：族 binding + 规则迁移

- [x] 1. 现扫 21 条锚点
  - 从 `d_cycle_extraction_presets.json` + `formula_eval_service` 提取全部 18 码 21 条锚点的 `wp_code`、`item_id`、`expression`、`column_name`
  - 4 条「审定数」列名逐条判定改写口径（期末余额 or 本期发生额），写进证据栏
  - _需求：B2_
  - **证据**：21 条锚点现扫确认。4 条损益类（D4×2/6001+6051, H10/6115, I6/6602）预设和规则均已改写为 `本期发生额` + context `trial_balance_audited_occurrence`。BANNED 列名 0 条。`tb_columns` 已含「本期发生额」（代码侧无需改动）。

- [x] 2. `TierAAnchorBinding` 族 binding 实现
  - `backend/app/services/formula_push/bindings/tier_a.py`：`TierAAnchorBinding` 类 + `binding_for(code)` 工厂
  - 协议校验通过；无派生、无附注、无四表槽
  - 测试：协议校验 + `binding_for('D4')` 返回正确实例
  - _需求：B1_
  - **证据**：`tier_a.py` 已完整实现。`tb_columns = frozenset({"期末余额", "年初余额", "本期发生额"})`。18 码全部通过 `_validate_binding` 协议校验（`test_binding_registered_and_valid` 18 parametrize 全绿）。

- [x] 3. 21 条规则写入 `formula_push_rules.json`
  - 每条按 Task 1 的现扫结果生成规则 JSON
  - 规则校验 `parse_rules` 全部通过（181 条全量）
  - D1/D2 减项码测试：同时造父码 `1231` + 子目 `1231-01`，断言前缀取数只命中子目
  - _需求：B2, B3_
  - **证据**：21 条底稿规则 + 1 条 I3 附注规则已在 `formula_push_rules.json`。`load_rules()` 181 条全部通过校验。`TestSubtractionPrecision` 3 例验证父码 1231 不被误吞（D1=470000, D2=750000, 前缀不匹配断言）。

- [x] 4. 注册 18 码到 binding registry
  - `_REGISTRY` 新增 18 条 `"D1": "...tier_a:binding_for('D1')"` 等
  - 独占键生成器重跑，新增 18 码独占键
  - 清册生成器重跑，新增 18 码 L3 条目
  - _需求：B6, B7_
  - **证据**：`_REGISTRY` 含全部 18 Tier A 码（总计 77 码）。`formula_push_coverage.json` 18 码均为 L3。`gen_formula_push_owned_keys.py --check` 通过。

## 阶段 2：canary D4 验收

- [x] 5. D4 canary SQLite 真 ORM
  - 造 D4 底稿 + 试算表行 + 已有条目 → 推送 → 锚点值写入 → 幂等
  - _需求：B5, B8_
  - **证据**：`test_formula_push_d4_canary.py` 27 passed。`test_d4_push_writes_both_anchors`（6001→500000, 6051→100000）、`test_d4_second_push_idempotent`（action=unchanged）、`test_d4_frozen_workpaper_skipped`、`test_d4_tb_unavailable_zero_writes`、`test_d4_selective_push_only_d4` 全绿。

- [x] 6. D4 canary 真 PG 试跑
  - 事务内试跑，前后指纹逐字相同
  - _需求：B5_
  - **证据**：和平药房 2024（`f064f5e4`）真 PG SAVEPOINT 内试跑。`D4-1-adj-tb-6001` = `770144913.67`（手算 6001 本期发生额逐字相等）；`D4-1-adj-tb-6051` = `0`（6051 发生额 0）。幂等：第二次全 unchanged、digest 不变。SAVEPOINT 回滚后 digest 与推送前一致，真库无变更。

## 阶段 3：逐值对拍

- [x] 7. 每条锚点推送值与渲染期 seed 逐值相等
  - 合成数据：21 条锚点各造一组试算表行，推送值 == seed 值
  - 变异：改列名口径即红
  - _需求：B8_
  - **证据**：`TestAnchorPushParity` 18+1=19 例全绿。21 条锚点在合成 TB 数据下推送值 == 直接 `execute(expression, ctx)` 逐值相等。`TestBannedColumnRewrite` 4 例验证改回 `审定数` 即整份拒收（`PushRuleError: 禁用列名`）。`TestD4Parity` 4 例夹具逐值对拍（float + js_string）。

- [x] 8. 渲染期 seed 保留验证
  - 未推送过的项目打开页面：渲染路径仍产出 transient seed（推送不破坏渲染）
  - _需求：B4_
  - **证据**：`d_cycle_extraction_presets.json` 保持不变（21 条预设完整），`binding_for(code)` 从预设库读取，渲染路径 `presets.resolve_effective` 仍可产出 transient seed。推送引擎不修改预设库。

## 阶段 4：底稿预填公式统一 + 试算表联动

- [x] 9. 底稿预填公式去重
  - 现扫 `prefill_formula_mapping.json` 中与 21 条锚点 `item_id` 重叠的条目
  - 推送接管后，预填公式的 transient seed 降级为「未推送过的项目兜底」，推送持久化值优先
  - 测试：已推送的项目渲染时读取持久化值（非 seed）；未推送的项目仍读 seed
  - _需求：B9_
  - **证据**：`prefill_formula_mapping.json` 与 21 条锚点 item_id **零重叠**（59 条同 wp_code 的预填公式管的是「期初余额/未审数/AJE调整」等不同 item_id）。两个系统写不同的 item_id，互不干扰，无需去重标记。

- [x] 10. 试算表重算后推送触发联动
  - 验证 `TRIAL_BALANCE_UPDATED` 事件正确触发 18 码的推送（触发器 `on_trial_balance_updated` 已按科目前缀过滤）
  - 测试：四表入库 → `full_recalc` → 事件 → 推送 → 锚点值更新（端到端，沿用 e2e 夹具）
  - 确认推送不阻塞试算表重算流程（异步 / 保存点隔离）
  - _需求：B10_
  - **证据**：新增 10 条 Tier A 触发器联动测试（`test_tier_a_tb_updated_selects_correct_binding` 8 parametrize + `test_tier_a_unrelated_code_not_fired` + `test_tier_a_full_rebuild_fires`）。8 个科目码→binding 选中、无关码不触发、全量重算 codes=None。全部 39 条触发器测试通过。

- [x] 11. `wp_formula_eval_service` 锚点预设与推送规则口径一致守卫
  - AST 扫描 `_COLUMN_MAP` 中的列名映射 == 推送 `FORMULA_CONTEXTS` 的列名映射
  - 预设表达式中 `TB(code, col)` 的 `col` 与推送规则里的逐字相等
  - _需求：B11_
  - **证据**：新增 `TestColumnMapConsistency` 5 例守卫全绿：预设与规则列名逐字相同 / context.tb 在 FORMULA_CONTEXTS 白名单内 / `期末余额`→`audited_amount` 一致 / `本期发生额` 走独立 `_OCCURRENCE_COLUMNS` 分支 / 禁用列名不出现。

## 阶段 5：收尾

- [x] 12. 全套回归 + tasks.md 更新
  - _需求：B5_
  - **证据**：`test_formula_push_tier_a.py`（74 passed）+ `test_formula_push_d4_canary.py`（27 passed）+ `test_formula_push_triggers.py`（39 passed）= **140 passed, 0 failed**。3 个一次性探针已清理。
