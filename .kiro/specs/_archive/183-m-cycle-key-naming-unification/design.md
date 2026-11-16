# Design — M 循环键名统一（占位）

> **状态：占位（2026-11-16 立项，未开工）**。本文件只记录两条候选路径的**代价与风险**，
> 供用户拍板 R1；拍板后再补完整设计。

## §1 现算事实（沿用原 spec design §14.1，不重复推导）

| 侧 | 形态 |
| --- | --- |
| 契约 | `review.html_store.shape = flat_key_value`；`store_item_id` 在 M1~M10 写成 `placeholder`；行身份 `row_identity_kind = template_row_key` |
| provider | `phase5_m_cycle_common.build_flat_store_projection` / `merge_flat_projection_into_store` / `store_item_id = {prefix}{sheet_key}` 全按 flat 形态实现 |
| 前端 | 明细表用**整表 JSON**（`{remark: JSON.stringify(detailRows)}`），键名驼峰；另有 flat `getField(sheet, field)` 并存 |
| 差异 | M1 18+19 条、M2 19+9 条 = **65 条**（`test_m_detail_keys_match_provider.py` 冻结为只许减小） |

## §2 两条候选路径

### 路径 A：统一收敛到 `flat_key_value`（改前端）

**做法**：前端 10 个 `useM{n}Detail.ts` 的整表 JSON 存储改为逐字段 flat 键（与 provider 的 `getField` 通路合并成一套），键名改为契约 `column_key`。

| 维度 | 代价 / 风险 |
| --- | --- |
| 改动面 | **10 个宿主**的读写语义 + 导入导出列 + 明细表渲染 |
| 契约 | **零改动** ⇒ digest 不变 ⇒ 已发布 representation 不脱钩、**无需重发布** |
| 存量数据 | 需把已存的整表 JSON 拆成 flat 键（M 循环真库行数需现算；`placeholder` store item 说明这些表可能**从未真正写入过**，须先核实） |
| 验证 | 真实 OO 往返（改一格 → forcesave → 裁决 → 核对发布文件） |
| 风险 | 前端行模型与模板列序绑定更紧，后续加列要三处同改 |

### 路径 B：按 sheet 分级声明（改契约）

**做法**：契约 `html_store.shape` 按 sheet 分级 —— 明细表声明 `row_array`、审定表声明 `flat`；前端保持整表 JSON。

| 维度 | 代价 / 风险 |
| --- | --- |
| 改动面 | 契约 `m*.json` 10 份 + provider 投影/合并函数 + `html_store` 解析层 |
| 契约 | **digest 变** ⇒ 已发布 representation 全部脱钩 ⇒ **须重发布所有 M 表** |
| 存量数据 | 前端整表 JSON 可原样保留（这正是它的现形态） |
| 验证 | 同上，且重发布本身要在真实项目上验 |
| 风险 | `html_store.shape` 是全局字段，按 sheet 分级要确认所有消费方（`store_mirror` / `store_materialize` / 前端 `debouncedSave`）都认新形态 |

## §2.1 现算更正（2026-11-16，任务 1.1~1.5 完成后）

原 §2 的两条路径建立在三条**已过期**的前提上，现算全部推翻：

| 原前提 | 现算结果 | 影响 |
|---|---|---|
| 前端明细表用整表 JSON 且有存量数据 | 明细表整表 JSON **0 行**（M 组 34 行全是 `M{n}-1-tb-amount` 审定表取数） | 路径 A 的「存量迁移」成本 = **0** |
| 10/10 张表都有 flat `getField` 并存 | 10 个 composable 里 `getField` 只有 1 处（M9） | 「两套通路并存」描述不成立 |
| 契约 `store_item_id` 写成 `placeholder` | 10 份契约全是 `store_item_id = None`，`placeholder` 现算 0 处 | 契约侧无需「修 placeholder」 |

**真实形态是三分的**：

| 表 | 前端存储 | 契约 |
|---|---|---|
| M1 / M2 / M3 / M7 / M9 / M10 | 整表 JSON（`*-full-data`）**+** 逐行 JSON（`*-row-N-data`） | flat_key_value / template_row_key / store_item_id=None |
| M4 / M5 / M6 / M8 | **只有**逐行 JSON（`*-row-N-data`） | 同上（完全一致） |

⇒ **修正后的路径 A'（本轮采纳）**：统一到「**逐行 JSON 单一来源**」。

- M4 / M5 / M6 / M8 **已经是目标形态，零改动**；
- M1 / M2 / M3 / M7 / M9 / M10 只需**删掉 `*-full-data` 这条并行写入**，让逐行 JSON 成为唯一来源；
- 契约侧**不动**（`store_item_id=None` 是合法的「无单一 store item」声明，逐行 JSON 走 `item_id` 前缀约定）；
- 存量数据迁移成本 = 0（明细表从未写入）；
- 剩下的是**键名层**：逐行 JSON 里的键（`{key, ...}`）与契约 `column_key` 的对应，
  由棘轮（M1 18+19 / M2 19+9 = 65 条）冻结，逐条偿还。

**这个修正让工作量从「改 10 个宿主的读写语义 + 迁移存量 + 重发布所有 M 表」降到
「删 6 个文件里的并行 full-data 写入 + 逐条对键名」，且不需要重发布任何 representation。**

## §3 建议

**倾向路径 A**，理由：

1. **不脱钩已发布 representation** —— 路径 B 的重发布代价在 M 循环（10 张表 × 真实项目）上不可控；
2. 契约里的 `store_item_id = placeholder` 是**明确的未完成标记**，说明 flat 形态本就是设计意图，前端整表 JSON 是历史实现；
3. 棘轮已在位（65 条只许减小），路径 A 可以**逐表推进**、每表独立验证，不必一次性切完。

**但需先核实一件事**：M 循环真库里这 10 张表**是否有真实数据**。若 `placeholder` 意味着从未写入，路径 A 的存量迁移成本为 0，应直接选 A；若有数据，要先算迁移脚本的行数与回滚方案。

## §4 开工时必做的现状 grep（原 spec 的教训）

- `git status` 核 HEAD（并发会话会前移分支）；
- 现读 `test_m_detail_keys_match_provider.py` 的基线（可能已被改动）；
- 现读 10 个 `useM{n}Detail.ts` 的存储形态（别按命名推）；
- 现算 M 循环真库行数（`checklist_responses` 按 `wp_id` + `item_id` 前缀）；
- 确认扫描器 `contract_field_names_scan.py` 对 `{sheet}` 参数拼键的识别缺口（原 spec design §14.3）。
