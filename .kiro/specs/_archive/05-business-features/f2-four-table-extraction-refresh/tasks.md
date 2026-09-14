# Implementation Plan

## Overview

把 F2-1 存货审定表四表库取数从「一次性静默 seed（口径不稳健、无刷新、公式不可见）」升级为「显式 TB() 公式驱动 + 可编辑 + 🔄刷新」。6 波 15 任务，灰度 `F2_FOUR_TABLE_EXTRACTION_ENABLED` 默认 False，各波独立可回退。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "W0", "name": "安全网 + 骨架", "tasks": ["1.1", "1.2", "1.3"] },
    { "id": "W1", "name": "取数服务 + 口径修正", "tasks": ["2.1", "2.2", "2.3"] },
    { "id": "W2", "name": "预设 + 读时收敛", "tasks": ["3.1", "3.2"] },
    { "id": "W3", "name": "公式管理 surface + 编辑校验", "tasks": ["4.1", "4.2"] },
    { "id": "W4", "name": "刷新入口 + provenance 面板", "tasks": ["5.1", "5.2"] },
    { "id": "W5", "name": "零回归门 + 端到端", "tasks": ["6.1", "6.2", "6.3", "6.4"] }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 安全网 + 骨架
  - [x] 1.1 Characterization 安全网
    - 编写 characterization 测试（`test_f2_extraction_characterization.py`）锁定灰度关时旧 `_build_adjudication_prefill` 对真实 tb_balance 数据的输出（opening/closing 各类别行），作为 Property 14 零回归基线
    - 同时锁定 F2-3~13 明细跨表带入 / F2-14 调整 / 附注联动 / 导入导出现有行为不受本 spec 影响
    - _Requirements: 6.1, 6.2, 7.1_
  - [x] 1.2 骨架 + 灰度开关 + F2_ANCHORS
    - `backend/app/core/config.py` 加 `F2_FOUR_TABLE_EXTRACTION_ENABLED: bool = False`
    - 新建 `backend/app/services/f2_extraction/__init__.py`
    - 新建 `f2_extraction/anchor_registry.py`：`F2_ANCHORS: frozenset[str]`（36 项 = 12 原值类×3 字段 + 1 跌价类×3 字段，从 `useF2Adjudication.ts::itemId` 格式生成）+ `is_known_anchor(anchor: str) -> bool` + `seed_field(anchor: str) -> str|None`（F2-1 全返 `'conclusion'`，对齐前端 `loadField` 读 `.conclusion`）
    - 契约守卫 `test_f2_anchor_contract.py`：断言 F2_ANCHORS 集合 == 前端 `useF2Adjudication` 的 `itemId(block,rowKey,field)` 穷举集（防漂移）；`is_known_anchor` 对集合内/外正确判定
    - _Requirements: 1.6, 6.4, 7.1_
  - [x] 1.3 Wave 0 核实：评估器列名 + PUT 校验分支
    - 核实 `wp_formula_eval_service._COLUMN_MAP`：确认**无**借方发生额/贷方发生额（已实证=无），记录到 design 复核备注
    - 核实 `PUT /api/workpapers/{wp_id}/formulas` 保存路径是否 hard-couple generic evaluator 求值（codegraph callers 追 `evaluate_wp_formula_expression` 在 PUT 分支的调用位置+条件）；确定 Wave 3 需改哪个 guard 让 F2 不走 generic eval
    - 产出：`docs/proposals/f2-extraction-wave0-findings.md`（事实记录+对 Wave 3 的预判）
    - _Requirements: 5.1, 5.2_

- [x] 2. Wave 1 — 取数服务 + 口径修正
  - [x] 2.1 `f2_extraction/extract.py` 核心取数
    - 新建 `F2_COLUMN_MAP = {'期初余额':'opening_balance','期末余额':'closing_balance','借方发生额':'debit_amount','贷方发生额':'credit_amount'}`
    - 新建 `parse_tb_formula(expression: str) -> tuple[str, str, bool] | None`（解析 `TB('account','列')` / `ABS(TB('account','列'))`；列 ∈ F2_COLUMN_MAP；非法→None）
    - 新建 `extract_f2_category_values(ctx, effective_bindings: list[dict]) -> dict[str, dict]`：
      - 对每条 binding，parse_tb_formula → (account, column, is_abs)
      - 查 `tb_balance WHERE account_code==account OR startswith(account)` + `get_active_filter` + `_is_leaf`（复用 `d_cycle_extraction.prefill._is_leaf` 或本地等价）
      - 叶子按 column SUM（跌价 is_abs 则 abs 后 SUM）
      - 跳过全零/无名叶子；无子科目→该锚点不产出
      - 返回 `{anchor: {value: float, account, column, is_abs, source_codes: [叶子码]}}`
    - 测试 `test_f2_extract.py`（Property 1/2/3/5/8/12）：只取叶子防双算 / 增=debit减=credit / 跌价 abs 反向 / 无数据不报错 / 公式驱动（改 account 改值） / 幂等
    - _Requirements: 1.2, 1.3, 4.1, 4.2, 4.3, 4.5, 5.4_
  - [x] 2.2 Tier B 口径修正：`_build_adjudication_prefill` 委托
    - `_f2_inventory_main.py::_build_adjudication_prefill`：
      - **灰度开**：委托 `extract_f2_category_values`（传默认 bindings = 全部 F2_CATEGORIES 的标准 opening/increase/decrease 公式），返回 `{rowKey: {opening, increase, decrease, closing}}`（新增 increase/decrease 不再让前端粗猜）
      - **灰度关**：保留旧路径逐字节不变（`_row_depth`+`by_depth[max]` + 只返 opening/closing）
    - render 输出 `tb_values` 结构：灰度开 `{rowKey: {opening, increase, decrease, closing}}`；灰度关 `{rowKey: {opening, closing}}`（现状）
    - 测试 `test_f2_prefill_gray.py`（Property 14）：灰度关 render 输出 == characterization 基线逐字节等价
    - _Requirements: 4.1, 4.2, 4.3, 6.1_
  - [x] 2.3 前端 seed 口径改直填
    - `useF2Adjudication.seedFromTbValues`：
      - 若 tbValues 含 `increase`/`decrease` 字段（灰度开）→ 直接填 opening/increase/decrease 三字段
      - 若只含 `opening`/`closing`（灰度关/旧结构）→ 保持旧 `closing−opening` 粗猜逻辑（零回归）
    - 删除灰度开时「粗猜」路径（本 spec 范围，灰度关保留向后兼容）
    - vitest `useF2Adjudication.seed.spec.ts`（Property 2/4/14）：灰度开直填 / 灰度关粗猜不变 / 手工/明细优先
    - _Requirements: 4.2, 4.4, 6.1_

- [x] 3. Wave 2 — 预设 + 读时收敛
  - [x] 3.1 预设库文件 + presets.py
    - 新建 `backend/data/f2_extraction/f2_extraction_presets.json`（见 design Data Models，39 条=12×3 + 1×3）
    - 新建 `f2_extraction/presets.py`：
      - `load_f2_presets() -> list[dict]`（mtime 缓存，结构与 d 循环 `presets.load_presets` 镜像）
      - `resolve_effective(db, wp_id, project_id) -> list[dict]`（预设 ∪ 用户 wp_formula，禁用>custom>预设，anchor 校验 `is_known_anchor`，未知丢弃+告警）
      - `f2_tier_a_semantic(expression) -> str`（标注「四表库未审取数（tb_balance）」语义消歧）
    - 测试 `test_f2_presets.py`（Property 6/7/13）：收敛唯一 / anchor 校验 / 恢复默认回落
    - _Requirements: 1.1, 1.6, 2.3_
  - [x] 3.2 接入 render：公式驱动取数
    - `_build_adjudication_prefill`（灰度开分支）改为先 `resolve_effective` 再传 `effective_bindings` 给 `extract_f2_category_values`
    - 效果：用户编辑某锚点公式后再 render → 取数按新公式变化（Property 8）
    - 测试 `test_f2_formula_driven.py`（Property 8/9）：F2 走 f2_extraction 不走 generic evaluator / 改公式改值
    - _Requirements: 1.1, 5.1_

- [x] 4. Wave 3 — 公式管理 surface + 编辑校验
  - [x] 4.1 公式管理 surfacing
    - `wp_surfaced_f.py`：F2 base 的 surfacing 分支，灰度开时调 `f2_extraction/surface.py::build_f2_surfaced_formulas(db, wp)`（每锚点一条：anchor/expression/sheet_codes=['F2-1']/semantic/value[从 extract_f2_category_values 取当前值]/source/tier='A'/editable=True）
    - surfacing 替换 F2-1 现有的模糊「取自 F2-3~13 明细」条目（灰度开）；灰度关保持原条目
    - _Requirements: 2.1, 2.4, 2.5_
  - [x] 4.2 保存校验 F2 列名分支
    - `wp_formula.py`（PUT /formulas）：对 F2 wp（通过 wp_code 前缀判定）追加保存校验分支：
      - `find_unsupported_formula_functions`（复用，拒 AUX/PREV/LEDGER）
      - F2 列名校验：从表达式 parse 列名，∉ {期初余额,期末余额,借方发生额,贷方发生额} → 422
      - **不走 generic `evaluate_wp_formula_expression` 求值**（F2 求值走 f2_extraction）
    - 测试 `test_f2_formula_save_validation.py`（Property 10/11）：借方发生额合法 / 审定数非法422 / AUX拒422
    - _Requirements: 5.2, 5.3, 2.2_

- [x] 5. Wave 4 — 刷新入口 + provenance 面板
  - [x] 5.1 前端 `F2FourTableSourcePanel.vue`
    - 镜像 `E1FourTableSourcePanel.vue`（同模式：各类别行展示 来源科目 + TB() 公式 + 期初/增加/减少/期末 + 🔄重新取数按钮）
    - 数据来源：render 返回的 `tb_values`（灰度开含 increase/decrease + formulas + source_codes）
    - 「🔄 从四表库刷新取数」按钮：
      - 编辑权限门控（`inject('isReadonly')` → 只读禁用）
      - 刷新前对每类别：若该类别对应锚点已有手工值（conclusion 非空）或 `isFromCrossSheet`（明细带入）→ `ElMessageBox.confirm` 提示「当前值将以四表库值覆盖，是否继续？」
      - 用户确认 → 用 render 已带的 tb_values 回填 allResponses 对应锚点 + debouncedSave 持久化
      - 面板底部展示 provenance（期初/增/减/期末 + 每字段 `TB('code','列')` 公式 + 叶子来源码）
    - `GtF2InventoryMain.vue`（F2-1 审定表 sheet 区间）顶部接入面板（灰度开时显示）
    - vitest `F2FourTableSourcePanel.spec.ts`（Property 4/15）：confirm 逻辑 / provenance 渲染
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - [x] 5.2 render 输出扩 provenance 字段
    - render `tb_values`（灰度开）每类别额外带 `formulas: {opening: expr, increase: expr, decrease: expr}` + `source_codes: [叶子码]`，供前端面板展示
    - _Requirements: 3.4, 7.2_

- [x] 6. Wave 5 — 零回归门 + 端到端
  - [x] 6.1 全量回归门
    - 跑全部 f2_extraction/ 测试（expect 全绿）+ characterization 基线（灰度关逐字节等价）+ F2 相关既有测试（导入导出/crossSheet/附注）
    - _Requirements: 6.1, 6.2, 7.1_
  - [x] 6.2 契约守卫 `test_f2_extraction_contract.py`
    - F2 预设/用户公式全走 `f2_extraction` 求值路径，不调 `evaluate_wp_formula_expression` 求值（grep 验证 + import 守卫）
    - F2_ANCHORS == 前端 itemId 穷举集（防漂移）
    - F2 列名集 == F2_COLUMN_MAP.keys()（防遗漏）
    - _Requirements: 5.1, 6.3, 6.4_
  - [x] 6.3 前端全量验证
    - `useF2Adjudication` seed vitest 全绿 + F2FourTableSourcePanel vitest 全绿 + `GtF2InventoryMain` Vite transform 200 + get_diagnostics 全清
    - _Requirements: 6.2, 7.1_
  - [x] 6.4* live round-trip（可选，需实例化含存货余额的项目）
    - render tb_values 新口径（灰度开）→ 面板展示 provenance → 🔄 刷新回填 → 公式管理编辑某类别公式（改 1401→1402）→ render 值随之变 → 恢复默认回落 → RESTORED_IDENTICAL 零污染
    - _Requirements: 3.5, 5.4, 7.2_

## Notes

- 灰度 `F2_FOUR_TABLE_EXTRACTION_ENABLED` 默认 False：关闭时 F2 表现逐字节等价当前，无刷新入口、无公式 surface、render 输出旧 `{opening, closing}` 结构。
- `f2_extraction` 是 F2 专属，**不改共享 `wp_formula_eval_service._resolve_tb`**（后者读 trial_balance 只支持审定/未审列，改它污染全平台 TB() 语义）。
- F2 `TB()` 列名四选：期初余额/期末余额/借方发生额/贷方发生额，全映射 tb_balance 列。trial_balance-only 列（审定数/未审数）在 F2 保存时 422 拒绝。
- F2-3~13 明细表项目级取数不在本 spec（tb_balance 无项目/规格维度，宁缺勿造）。
- 迁移：无 DB 迁移（F2 预设用文件 + 用户公式复用 wp_formula 现有表）。
- 前端刷新是用 render 已带的 `tb_values`（不新增后端端点），避免增加 HTTP 往返。若后续需绕过 render 缓存实时重查，可加轻量 `POST /f2/refresh-extraction` 端点（当前不需要）。
