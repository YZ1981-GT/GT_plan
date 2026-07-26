# Design Document

## Overview

把调整分录导入导出契约收敛为一处可核查、有守卫的真源，分五波交付：

- **Wave 0（中央 4 项确定性缺陷）**：`mode` 真传递、示例行判定收紧、汇总导出补「类型」列 + sheet 名兜底、模板下载入口统一。独立可发布可回退。
- **Wave 1（底稿 Sheet_Spec 三重对齐）**：`item_id` + `storage_field` + `field_keys` 逐 sheet 对齐前端，`K2-3` 补注册。
- **Wave 2（K12-3 存储结构收敛）**：前端迁 JSON 数组（用户已定），带 per-field 回退读。
- **Wave 3（契约守卫）**：机器可读契约清单作单一真源，后端 + 前端双侧守卫。
- **Wave 4（Round_Trip + 零回归门）**。

全程 additive：不改富模板列集合、不改 `syncToCentral`/`sync-from-workpaper` 幂等链、不改 `recalc` 聚合口径。

## Architecture

### 三条通道与本 spec 的介入点

```
中央通道
  GET  /adjustments/export-template ──► 富模板(4 sheet, 项目科目库+下拉+联动)   [不改列集合]
  GET  /adjustments/export-summary  ──► _write_adj_sheet(7列, 无「类型」)      [W0-3 补列]
  POST /api/import-templates/adjustments/import
        └─ parse_import_data ──► _is_example_row(前6行, 过半即跳)              [W0-2 收紧]
        └─ _dispatch_import(mode=...) ──► _import_adjustments(无 mode 形参)     [W0-1 传 mode]
                                     └─ AdjustmentService.create_entry

底稿通道（数据驱动，单一工厂）
  create_cycle_import_export_router(api_prefix, specs, storage_field="conclusion")
        ├─ POST /{prefix}/export-template  (headers)
        ├─ POST /{prefix}/export-data      (headers + field_keys ← checklist_responses[item_id][field])
        └─ POST /{prefix}/import-data      (headers → field_keys → 写 item_id/field)   [W1 对齐三重键]

底稿 → 中央（本 spec 不动）
  useAdjustmentCentralSync.syncToCentral ──► POST /adjustments/sync-from-workpaper
        (source_ref 幂等 / origin='workpaper' / COLLABORATION_LOCKED)
```

### 已核实的漂移三维度（实现以代码为准，本表为 W1 的施工图）

`create_cycle_import_export_router` 的 `storage_field` **默认 `"conclusion"`**，而 7 张调整 sheet 均未显式声明 → 即使 `item_id` 改对，导入仍写 `conclusion` 列而前端读 `remark`。故对齐必须同时覆盖三维。

| sheet | 后端 `item_id` | 前端 Storage_Key | 后端写入列 | 前端读列 | `field_keys` 差异（后端 → 前端） |
|-------|---------------|-----------------|-----------|---------|--------------------------------|
| K2-3 | **无 spec** | `K2-3-adj-entries` | — | `remark` | 需新建：前端 `seq/entryType/summary/debitAccount/debitAmount/creditAccount/creditAmount/preparedBy`（借贷科目分列，与其余 sheet 不同构） |
| K3-3 | `K3-3-rows` | `K3-3-adj-entries` | `conclusion` | `remark` | 后端多 `noteRef`/`voucherNo`；前端多 `preparedBy` |
| K4-3 | `K4-3-rows` | `K4-3-adj-entries` | `conclusion` | `remark` | 后端多 `noteRef`/`voucherNo`；前端多 `entryNo`/`offsetAccount`/`preparedBy`/`source` |
| K5-3 | `K5-3-rows` | `K5-3-entries`（**无 adj**） | `conclusion` | `remark` | 金额键：后端 `debitAmount`/`creditAmount` → 前端 **`debit`/`credit`**；后端多 `noteRef`/`voucherNo`；前端多 `indexRef` |
| K7-3 | `K7-3-rows` | `K7-3-adj-entries` | `conclusion` | `remark` | 后端 `accountCode`/`noteRef`/`voucherNo` → 前端 **`reportItem`/`noteItem`/`indexRef`**（列结构不同构） |
| K8-3 | `K8-3-rows` | `K8-3-adj-entries` | `conclusion` | `remark`（双读 `remark ?? conclusion`） | 后端 `description`(调整事项说明) + `summary`(摘要) **双列**，前端只有 `summary` 担任「调整事项说明」；后端 `entryType` 缺失、前端用 `category`（报表调整/账项调整/其他） |
| K12-3 | `K12-3-rows`（JSON 数组） | per-field `K12-3-entry-{n}-{field}` | `conclusion` | 各 field 行 | 结构级不匹配；前端行模型 `index/type/description/accountCode/accountName/debitAmount/creditAmount/refIndex/remark` |

**真正无漂移、本 spec 不动**（3 张）：`K9-3`（spec 显式 `storage_field="remark"`）、`K11-3`（router 级 `storage_field="remark"`）、`K13-3`（spec 显式）。

**Task 1.1 characterization 修正的误判**（4 张，纳入 Wave 1）：`K1-4`、`K6-3`、`I5-3`、`I6-3` 的 `item_id` 正确但均未声明 `storage_field` → 取工厂默认 `conclusion`，而前端读写 `remark`：

| sheet | 前端读写列 | 有效 `storage_field` | 修法 |
|-------|-----------|---------------------|------|
| K1-4 | `remark`（`useK1Adjustment` / K1-7·K1-12 推送） | `conclusion` | 加 `"storage_field": "remark"` |
| K6-3 | `remark`（`K6TabAdjustment.persistEntries`，读 `remark ?? value`） | `conclusion` | 同上 |
| I5-3 | `remark`（`useI5Adjustment` / `useI5CrossSheet`） | `conclusion` | 同上 |
| I6-3 | `remark`（`useI6Adjustment` / `i6AdjDraftHelpers`） | `conclusion` | 同上 |

次要观察（Wave 1 若规范化需同步）：`K11-3` headers 第 6 列字面量是 `"……"` 占位而 `field_keys` 对应 `summary`；`K13-3` 用 `refIndex` 而其余用 `indexRef` 且多首列 `type`。

### 关键设计决策

**决策 1：对齐方向 = 改后端 Sheet_Spec 靠向前端，不改前端存储键**（K12-3 例外）。理由：前端 Storage_Key 已被多方消费——`useAdjustmentCentralSync.itemId`（同步到中央的 `source_ref` 组成部分）、跨 tab 推送（`K8TabDetail`/`K8TabContractCheck` 直接写 `K8-3-adj-entries`）、以及线上已有用户数据。改前端键会同时打断中央同步幂等性与既有数据可读性；改后端 spec 是纯 additive 且无存量数据代价（导入此前写的 `KX-3-rows/conclusion` 是 Orphan_Key，前端从未读到，无价值不迁移）。

**决策 2：`storage_field` 一律显式声明 `"remark"`**（不依赖工厂默认 `conclusion`），与前端 `emit('save', key, { remark: JSON.stringify(rows) })` 对齐。不启用 `dual_write`：双写会让 `conclusion` 残留半新半旧副本，反而制造第二真源。

**决策 3：中央 `overwrite` 语义 = 按 `adjustment_no` 的 by-key upsert，不清空全年**。

> **Task 1.2 实施补充（必要，否则幂等不成立）**：`AdjustmentService.create_entry` 自动生成 `adjustment_no`（`_next_adjustment_no` = 同类型分录组计数+1，且**计入已软删组**），不落文件编号。若照字面"软删 existing + 创建新组"实现，第 1 次覆盖后新组编号变成 `AJE-002`，第 2 次用文件的 `AJE-001` 就匹配不上 → Property 1 幂等失效。故 overwrite 模式且文件提供显式编号时，新建组后追加一条 `UPDATE adjustments SET adjustment_no=文件编号` 把编号钉住（语义：**overwrite 模式以文件编号为权威键**）；`append` 模式完全不受影响。
> 另：`mode` 实现为 keyword-only（`(..., user, db, *, mode="append")`）以保留既有 5 个位置参数契约；无编号行（`__auto_*`）无 by-key 键，两种模式均为追加；`skipped_rows` 仅在真有跳过项时附带（保 append 返回结构逐字节不变）；`pending_review` 既有组不在 4 类判定内，`delete_entry` 抛错 → 落 `failed_rows` 并继续（符合 Error Handling，非 skipped）。理由：`origin='manual'` 既包含"中央导入产生"也包含"用户在中央页手工新建"，按年度清空 manual 会误删后者（不可逆）。by-key 覆盖同时满足 R1.1（同文件重复上传不成倍追加）与 R1.3（不碰 workpaper-origin/approved），且语义可解释："文件里有的编号覆盖，文件里没有的保留"。跳过项（approved / 活跃协作 / origin=workpaper 撞号）计入 `skipped` 并给出原因。

**决策 4：示例行判定改「全部可比字段逐字相等」**（`match_count == len(matchable_pairs)`），保留前 6 行窗口与数值规范化 `_norm`。模板内置示例仍能全等命中被跳过；用户覆盖填写只要任一字段不同即为数据行。

> **Task 1.3 实施补充（本决策的单示例假设不足）**：①富模板实际有 **4 行内置示例**（AJE/RJE 各借贷两行），只有 AJE 第 1 行与 `TEMPLATE_COLUMNS` 单示例一致 → naive 全等会让另 3 行示例变脏数据（破 Property 5 硬门）。故新增 `TEMPLATE_EXAMPLE_ROWS` 内置示例行登记表，全等判定对**任一候选示例行**成立即跳过；将来任何类型上多示例模板都必须在此登记。②**hypothesis 抓到的漏洞**：示例金额 `0` 被读取端 `str(v or "")` 读成 `""`，若空值算"不可比"，用户在该格填真实金额仍被吞 → `_example_comparable_pairs` 对**数值列示例为空按 0 参与比较**（模板公式自动填充列仍不可比以保 Property 5）。③示例跳过发生在 **parse 阶段**，经 `parse_import_data(..., stats=)` 出参回报，端点以 `example_skipped_count`（仅 >0 才附带）呈现，**不折进 `skipped_count`**，保住决策 3 的 `skipped_count ≡ len(skipped_rows)` 不变量与 append 返回结构逐字节等价。④反向收益：其余 6 种 import_type 此前同样存在"部分匹配吞真实数据"缺陷，收紧后一并修好（实测全 7 类内置示例仍被跳过）。

**决策 5：汇总导出补「类型」列 + 解析器 sheet 名兜底双保险**。列插在「编号」之后与富模板列序一致；解析器兜底仅在「类型」列缺失时生效，列存在则以列为准（R3.3）。

> **Task 1.4 实施补充（光补列 Property 6 不成立）**：①`validate_import_file` 从不做**表头别名规范化**（`科目名称→二级科目名称` 的别名此前只存在于 `parse_import_data` 内的局部字典），而汇总导出用「科目编码/科目名称」→ 补完「类型」后校验仍判「缺少必填列: 二级科目名称」拒收整表。故把**表头别名 / 候选 sheet 判定 / 类型推断**三者抽为模块级单一真源供 validate 与 parse 共用（顺带修好"旧 7 列模板 / `分录编号` 等 legacy 表头过不了校验"这一 pre-existing 缺陷）。②类型兜底的一致性判定必须按 **parse 会读的全部候选 sheet** 求交（validate 只选首个匹配 sheet，若只看它会出现"校验过了但 parse 的第二个 sheet 仍缺类型"）：只有全部候选 sheet 都可判别才免除「缺少必填列: 类型」。③冲突走 `warnings` 不阻断，`stats["type_source_conflicts"]`/`["type_inferred_from_sheet"]` 均"非空才带"。④`_write_adj_sheet` 有**三条写行路径**（带 line_items / 无明细汇总行 / 扁平兼容），补列须同步全部列偏移。⑤保持不变的既有缺陷（超范围）：`parse_import_data` 的别名规范化对所有 import_type 一律套用，对 `trial_balance` 会把「科目名称」映成不在其列集合的键而丢列，仅加注释说明。

**决策 6：K12-3 前端迁 JSON 数组 + per-field 回退读**。写只写 `K12-3-rows`(`remark`, JSON 数组)；读优先 JSON，为空时回退扫 per-field 键重建（历史数据不丢），重建后首次保存自然收敛为 JSON。旧 per-field 键不主动删除（避免不可逆），由后续清理任务处理。

**决策 7：契约守卫的单一真源 = 机器可读契约清单**。后端测试读不到前端 `.vue`，前端 vitest 读不到 Python `_SPECS`。故新增 `backend/data/adjustment_ie_contract.json` 作双侧共同真源：后端守卫断言 `_SPECS` 与清单一致（含 `item_id`/`storage_field`/`field_keys`），前端 vitest 守卫断言各调整 tab 的 `ITEM_PREFIX + '-entries'` / `itemId` 与清单一致。任一侧改动而未同步清单即 CI 失败。清单含 `exempt` 段登记显式豁免（R7.4）。

## Components and Interfaces

### 后端

**`app/routers/import_templates.py`**
- `_dispatch_import`：`adjustments` 分支改为 `_import_adjustments(rows, project, y, mode, user, db)`。
- `_import_adjustments(..., mode: str = "append", ...)`：新增 mode 形参；`mode == "overwrite"` 时对本次文件出现的每个 `adjustment_no`，先查同项目同年度同编号的既有分录组 → 可覆盖则软删旧组再创建新组，不可覆盖（approved / 活跃协作 / `origin='workpaper'`）则跳过并累加 `skipped` + `skipped_rows` 原因；`append` 分支逐字节保持现状。
- 覆盖后复用既有删除路径触发试算表重算（不新造 recalc 调用）。

**`app/services/import_template_service.py`**
- `_is_example_row`：判定改全等；返回契约不变（`bool`）。
- `parse_import_data`（两处调用点）：被跳过的示例行计入 `skipped`（或独立 `example_skipped`），不计 `failed`。
- 类型 sheet 名兜底：解析 adjustments 时，若列集合缺「类型」而 sheet 名匹配 `AJE`/`RJE` 关键词，则为该 sheet 全部行注入类型；列存在则忽略 sheet 名。

**`app/routers/adjustments.py`**
- `_write_adj_sheet(ws, entries, adj_type)`：`headers` 插入「类型」，每行写入 `adj_type`（函数已接收该参数，当前仅用于未写入的语义标识）。

**`app/routers/wp_render_strategies/_k{2,3,4,5,7,8,12}_import_export.py`**
- 逐 sheet 按上表调整 `item_id` / 新增 `storage_field: "remark"` / 重写 `headers` + `field_keys` 对齐前端行模型；`_K2_SPECS` 新增 `K2-3` 条目。
- `_cycle_import_export_common.is_numeric_field_key`：新增数值字段（如 `debit`/`credit`）需纳入白名单，否则金额被当字符串。

**`backend/data/adjustment_ie_contract.json`**（新建，双侧守卫真源）
```json
{
  "sheets": {
    "K3-3": { "item_id": "K3-3-adj-entries", "storage_field": "remark",
              "field_keys": ["seq","entryType","summary","accountCode","accountName",
                             "debitAmount","creditAmount","preparedBy","remark"] }
  },
  "exempt": { "<sheet>": "原因" }
}
```

### 前端

- `UnifiedImportDialog`（或调整分录导入弹窗）：「下载导入模板」改指向项目感知富模板 `GET /adjustments/export-template`；无项目上下文时降级通用裸模板并提示无下拉。
- `useK12Adjustment`：`persistEntries` 改写 `K12-3-rows`（`remark`，JSON 数组）；`restoreEntries` 优先解析 JSON，为空回退现有 per-field 扫描重建。
- 各调整 tab：**不改** Storage_Key、行模型、`syncToCentral` 配置。

## Data Models

### Import_Mode 覆盖判定（决策 3）

```
for adjustment_no in 文件内出现的编号集合:
    existing = 查同 project_id + year + adjustment_no 且未软删
    if existing is None:                        → 创建（imported）
    elif existing.review_status == 'approved':   → 跳过（skipped: 已审批锁定）
    elif 存在活跃协作(entry_group_id):            → 跳过（skipped: 协作中）
    elif existing.origin == 'workpaper':         → 跳过（skipped: 底稿同步来源，请在来源底稿修改）
    else:                                        → 软删 existing + 创建新组（imported）
```
`append` 模式不进入本判定，行为不变。

### K12-3 存储收敛（决策 6）

| 阶段 | 写 | 读 |
|------|----|----|
| 现状 | per-field `K12-3-entry-{n}-{field}` | per-field 扫描重建 |
| 目标 | `K12-3-rows`（`remark`，`K12AdjustmentEntry[]` JSON） | JSON 优先 → 为空回退 per-field 重建 |

## Correctness Properties

### Property 1: Overwrite 幂等
同一文件以 `mode=overwrite` 连续导入 N 次（N≥2），最终分录组集合与导入 1 次等价（编号集合、每组明细行、借贷金额一致），且不产生重复组。
**Validates: Requirements 1.1, 9.1**

### Property 2: Append 逐字节不变
`mode=append` 的导入结果（imported/skipped/failed 计数与落库分录）与改动前实现完全一致。
**Validates: Requirements 1.2, 8.1**

### Property 3: Overwrite 覆盖范围安全
对任意既有分录组，若其 `origin='workpaper'` 或 `review_status='approved'` 或存在活跃协作，则 overwrite 后该组仍存在且字段未变，并在响应 `skipped` 中可见。
**Validates: Requirements 1.3, 1.4, 1.5, 9.6**

### Property 4: 示例行判定单调
数据行与 Example_Row 全部可比字段相等 ⟺ 被跳过；任一可比字段不同 ⟹ 必被当作数据行导入。被跳过的示例行不计入 `failed`。
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 9.2**

### Property 5: 模板示例仍被跳过
以内置示例原样提交的模板，其示例行仍被识别并跳过（收紧判定不得让示例行变成脏数据）。
**Validates: Requirements 2.5**

### Property 6: 汇总导出可被导入接受
`export-summary` 产物的列集合 ⊇ 中央导入必填列集合；该产物直接提交导入不因缺列被拒。
**Validates: Requirements 3.1, 9.3**

### Property 7: 类型来源优先级
「类型」列存在时以列值为准；缺列且 sheet 名可判别时以 sheet 名兜底；两者冲突时以列为准并给出提示。
**Validates: Requirements 3.2, 3.3**

### Property 8: 导出→导回业务等价
汇总导出未修改原样以 `overwrite` 导回后，中央分录集合业务等价于导出前（编号、金额、类型不失真）。
**Validates: Requirements 3.4, 9.3**

### Property 9: 无 Orphan_Key（三方键一致）
对契约清单内每张 sheet：后端 `item_id` 与 `storage_field` 等于前端实际读取的键与列；后端 `field_keys` 与前端行模型字段名逐字一致（除显式映射项）。
**Validates: Requirements 5.1, 5.2, 5.4, 7.1, 9.4**

### Property 10: 导出字段完备
每张 sheet 的导出 `headers`/`field_keys` 覆盖前端行模型全部用户可填字段（计算列除外），用户填写的任何有效列在导入后均可回读。
**Validates: Requirements 5.2, 5.3, 9.5**

### Property 11: 注册完整性与豁免可区分
前端存在调整分录持久化键的 sheet，必然在契约清单的 `sheets` 或 `exempt` 中出现；遗漏即失败。
**Validates: Requirements 5.5, 7.3, 7.4**

### Property 12: K12-3 结构收敛且不丢数据
迁移后写入仅产生 JSON 数组键；仅有 per-field 历史数据时读取结果与迁移前一致；JSON 与 per-field 同时存在时以 JSON 为准。
**Validates: Requirements 6.1, 6.2, 6.3**

### Property 13: 无漂移 sheet 行为不变
`K9-3/K11-3/K13-3` 的导入导出产物与落库键在改动前后逐字节等价。`K1-4/K6-3/I5-3/I6-3` 仅 `storage_field` 从 `conclusion` 改为 `remark`（Task 2.7），其 `item_id`/`headers`/`field_keys` 逐字节不变。
**Validates: Requirements 5.7, 8.1**

### Property 14: 上游链路不变
`syncToCentral`/`sync-from-workpaper` 的 `source_ref` 幂等、`origin='workpaper'`、协作锁行为，以及 `recalc` 的头表聚合 + workpaper 过滤行为，在本 spec 前后一致。
**Validates: Requirements 8.2, 8.3**

## Error Handling

- **导入分发**：`mode` 非法值 → 视为 `append`（不抛 500）；`project_id` 缺失沿用既有 400。
- **覆盖跳过**：跳过不算失败，`skipped` + 可读原因返回；单编号覆盖失败（如软删冲突）计入 `failed_rows` 并继续处理其余编号，不整批回滚。
- **类型兜底**：sheet 名无法判别且列缺失 → 保持既有"缺少必填列: 类型"错误（明确提示优于静默猜测）。
- **底稿导入**：`headers` 与文件列头不匹配 → 沿用工厂既有列校验错误；`item_id` 写入前的 `working_paper` 查询失败沿用既有 `ValueError`。
- **契约守卫**：清单与实现不一致时失败信息必须指名具体 sheet + 字段（不得只报"不一致"）。
- **K12-3 读取**：JSON 解析失败 → 回退 per-field 重建 + 前端 warning，不清空用户数据。

## Testing Strategy

- **Characterization 基线（W0 先行）**：锁定 `append` 导入、富模板导出、`_is_example_row` 对内置示例的判定、7 张无漂移 sheet 的导入导出产物，作为 Property 2/13 对照。
- **PBT**（hypothesis `max_examples=5`）：Property 1/3/4/8/12 用生成式；Property 6/9/10/11 用注册表/清单遍历式断言（不硬编码逐条清单）。
- **契约守卫**：后端 `tests/` 一支遍历 `_SPECS` 对照契约清单；前端 vitest 一支遍历各调整 tab 源文件的键声明对照同一清单。
- **Round_Trip 实测（W4）**：每张受影响 sheet 走 导出模板 → 填 → 导入 → 前端回显同值；`200` 不作为通过依据。可用鉴权 HTTP round-trip + 前端读取键断言替代浏览器，但必须验证到"前端读取键有值"这一层。
- **零回归门**：中央导入导出、各底稿 IE、`adjustments`/`trial_balance`/`adjustment_sync` 相关既有测试全量通过；禁止放宽断言或跳过用例。
