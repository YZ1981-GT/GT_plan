# M2/M3/M4/M7/M10 双向回写管线 · 需求

## 引言

**目标**：为 M2（实收资本）/ M3（库存股）/ M4（资本公积）/ M7（专项储备）/ M10（其他权益工具）五条 entry 走通 `workpaper_sync` 双向回写管线，解除 BP-1 / BP-2 / BP-3 三个阻塞项，使底稿内容能在 HTML 侧与 OnlyOffice 侧真正双向同步。

**上游依赖**：
- `m2-m3-m4-m7-m10-sheet-map-drift-and-collapse`（25/25 ✅ + 3 `[ ]*`，已完成 SHEET_MAP 错位 / BP-12 死代码 / BP-8 粒度折叠 / BP-6 mode 统一等前置修正）
- `m-cycle-sync-foundation-and-first-canary`（MC-1~29 共同裁决 + canary M6）
- `m-cycle-bidirectional-pipeline`（M1/M5/M8/M9 四条 entry 管线，格式参照）
- `m1-m5-m8-m9-mode-value-and-carrier-exceptions`（27/27 ✅，载体/mode 前置准备）

**scope**：本 spec 只覆盖 M2/M3/M4/M7/M10 五条 entry（BP-4 主轴的 lane 2）。M1/M5/M6/M8/M9 由其他 spec 覆盖。

**权威模板（现算）**：

| entry | 权威册 | sheets | 公式格 | 科目码 | 科目性质 | ITEM_PREFIX | 受管明细表 |
|---|---|---|---|---|---|---|---|
| M2 | M2 实收资本（股本）.xlsx | 11 | 302 | 4001 | 权益类 | `M2-` | 明细表（非上市）M2-2 + 明细表（上市）M2-2 |
| M3 | M3 库存股.xlsx | 10 | 72 | 4102 | 权益类 | `M3-` | 明细表M3-2 |
| M4 | M4 资本公积.xlsx | 9 | 89 | 4002 | 权益类 | `M4-` | 明细表M4-2 |
| M7 | M7 专项储备.xlsx | 10 | 56 | 4301 | 权益类 | `M7-` | 明细表M7-2 |
| M10 | M10 其他权益工具.xlsx | 11 | 125 | 4001 | 权益类 | `M10-` | 明细表M10-2 |

---

## Requirement 1：BP-1 解除 —— per-entry contract + authority model + definition bundle

**User Story:** 作为底稿双向回写系统，我需要每条 entry 有经审批的语义契约和定义包，这样 materialize / extract / merge 三个阶段才有可执行的字段级规范。

### 验收准则

1. WHEN 为五条 entry 各创建 contract JSON THEN 系统 SHALL 产出 5 份 `backend/data/workpaper_sync_contracts/m{n}.*.json`，格式为 `contract-definition:v1`。
2. WHEN 契约声明受管 sheet THEN 每份 SHALL 至少包含**明细表**（`xx-2`）；M2 SHALL 包含两张同码明细表（上市/非上市各一份字段映射）。
3. WHEN 契约声明字段 THEN 每个 field SHALL 有 `stable_field_key` / `json_pointer` / `mode`（editable 或 formula）/ `value_type` / `source_ref` / `cell`，且 mode 必须与 openpyxl 现算一致。
4. WHEN 契约声明 HTML 侧存储 THEN `review.html_store` SHALL 引用 `checklist_responses` 表，`item_id` 前缀与 `useM{n}FormData.ts` 的 `ITEM_PREFIX` 一致。
5. WHEN authority model 被选择 THEN 系统 SHALL 使用 `projection_contract`（与 D/M1/M5 同型）。
6. WHEN definition bundle 被发布 THEN 系统 SHALL 按 DAG `template → instrumentation → contract → bundle` 顺序发布。
7. WHEN adapter 被注册 THEN `_ALLOWED_PROVIDER_MODULES` 白名单与 `DELIVERED_PER_ENTRY_CONTRACTS` 台账 SHALL 数量一致且成对。

## Requirement 2：per-entry provider 与共享内核

**User Story:** 作为底稿渲染系统，我需要每条 entry 注册到 adapter registry，这样运行时能按 entry_id 找到正确的 contract 和 sync 策略。

### 验收准则

1. WHEN provider 被创建 THEN 系统 SHALL 产出 5 个 `phase5_m{n}_*.py`，走 `phase5_m_cycle_common.py` 共享内核。
2. WHEN provider 被 import THEN `build_m_provider(CONFIG)` SHALL 成功返回 namespace 且 `attach_pilot_adapters` 可调用。
3. WHEN M2 的两张同码明细表被声明 THEN `CONFIG.sheets` SHALL 包含 2 个 `MSheetConfig`，sheet_key 分别用 `m201-unlisted-managed` 和 `m202-listed-managed` 区分。
4. WHEN M4 的两级分组被声明 THEN 数据区 SHALL 覆盖分组合计行 + 子项行（R10~R19）。

## Requirement 3：BP-2 / BP-3 解除（阻塞）

**User Story:** 作为质控，我需要知道本 spec 的 finalize / OO 探针 / 端到端闭环为什么暂不能验。

### 验收准则

1. WHEN DAG 发布被排期 THEN 系统 SHALL 标 `[ ]*`：真库无 M 循环底稿 working_paper 记录 → 无法 resolve target。
2. WHEN OO 探针被排期 THEN 系统 SHALL 标 `[ ]*`：需真实 OO 9.4 环境。
3. WHEN 端到端闭环被排期 THEN 系统 SHALL 标 `[ ]*`：真库无有效业务载荷。

## Requirement 4：M2 同码双 sheet 的特殊处理

**User Story:** 作为实施者，我需要 M2 的两张同码明细表在契约层有不同的 sheet_key，这样上市与非上市数据不会互相覆盖。

### 验收准则

1. WHEN M2 契约被生成 THEN 系统 SHALL 包含 2 个 sheet 声明（非上市 15e+9f=24 列 / 上市 21e+15f=36 列）。
2. WHEN M2 审定表被分析 THEN 系统 SHALL 确认其全公式引用非上市明细表，不做 instrumentation。
3. WHEN sheet_key 被定义 THEN 不得含 MC-10 的空格缺陷。
