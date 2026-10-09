# Design — D4-4 调整分录汇总双向回写

## 1. 定位与参照

D4-4 走**单区动态行表**范式，与已落地的 D4-19（`phase5_d4_discount_sheet.py`，251 行）近乎同构。
本设计的主线就是「照 D4-19 复刻 + 处理 4 处差异」，不引入任何新引擎能力。

| 维度 | D4-19（参照） | **D4-4（本 spec）** | 差异处置 |
|---|---|---|---|
| sheet | `销售折扣与折让检查D4-19` | `营业收入调整分录汇总D4-4` | — |
| 范围 | A1:P36 | **A1:J23** | — |
| 表头 | 两级（R11 组 + R12 子列） | **单级 R5** | `header_rows: 1`（同 D4-19 契约值） |
| 数据区 | R13~R23 | **R6~R20** | — |
| footer | R24 marker `三、审计说明` | **R21 marker `提示：`** | 同机制，仅换 marker 串 |
| 受管列 | A-D + F-N（13 列） | **A~J（10 列，连续无跳）** | 更简单 |
| formula_mask | E 列 13~23（折扣比例派生） | **空** | 数据区公式格现算 0 |
| UUID 列 | **注入列 P**（模板无空列） | **现成空列 K** | 无需注入，K~O 本就空 |
| 行身份键 | `id` | 🔴 **`rowId`** | 不可照抄 |
| 行身份格式 | 单一 | 🔴 **两种并存** | 见 §4 |
| store | `D4-19-rows`（list） | `D4-4-rows`（list） | 同为 list，走 rows 循环 |

**为什么用 footer marker 而不是「无 footer」**：`footer_anchor` 在引擎侧确实可选
（`contracts.py:712` 为 `FooterAnchorSpec | None = None`），且有 3 个无 footer 的 D4 provider 先例
（`_erp_check_sheet` / `_other_margin_sheet` / `_product_margin_sheet`）—— 但那 3 个都是**静态区**
（无动态行表，故无需下界）。D4-4 是**动态行表**，footer marker 正是引擎判定「插行插在哪」的锚；
R21 的提示文本天然可做 marker。用它同时满足 Req 6.4（插行不得覆盖提示文本）。

## 2. 后端 provider：`phase5_d4_adjustment_sheet.py`

新建文件，结构逐节对齐 D4-19。

### 2.1 常量

```python
ENTRY_ID = "xlsx/gt-d4-operating-revenue"          # 共享 entry，不建独立 entry
TEMPLATE_RELATIVE_PATH = "D/D4 收入底稿.xlsx"       # 与其余 D4 provider 同一权威册

MANAGED_SHEET_D44 = "营业收入调整分录汇总D4-4"
TEMPLATE_ID_D44   = "D44"
SHEET_KEY_D44     = "d44-managed"
STORE_ITEM_ID_D44 = "D4-4-rows"
TABLE_KEY_D44     = "d4_4_rows"
ROW_IDENTITY_KEY_D44 = "rowId"                     # 🔴 非 'id'

HEADER_ROW_D44     = 5
FIRST_DATA_ROW_D44 = 6
LAST_DATA_ROW_D44  = 20
FOOTER_ROW_D44     = 21
FOOTER_MARKER_D44  = "提示："                       # A21 前缀
MANAGED_LAST_COL_D44 = "J"
UUID_COL_D44         = "K"                          # K~O 全空，取首个
```

### 2.2 字段表

```python
MANAGED_FIELD_SPECS_D44 = (
    # (field,          col, mode,       value_type, json_key,      header_text)
    ("description",    "A", "editable", "text",   "description",  "调整事项说明"),
    ("category",       "B", "editable", "text",   "category",     "类别（报表调整/账项调整/其他）"),
    ("reportItem",     "C", "editable", "text",   "reportItem",   "报表项目"),
    ("accountName",    "D", "editable", "text",   "accountName",  "科目名称"),
    ("noteItem",       "E", "editable", "text",   "noteItem",     "附注项目"),
    ("placeholder",    "F", "editable", "text",   "placeholder",  "……"),
    ("debitAmount",    "G", "editable", "amount", "debitAmount",  "借方调整金额"),
    ("creditAmount",   "H", "editable", "amount", "creditAmount", "贷方调整金额"),
    ("indexRef",       "I", "editable", "text",   "indexRef",     "索引"),
    ("remark",         "J", "editable", "text",   "remark",       "备注"),
)

_FORMULA_MASK_D44: tuple[str, ...] = ()   # 空：数据区公式格现算 0
```

🔴 `stable_field_key` 经 `_snake()` 得 `d4_4_rows/{identity}/report_item` 等**全小写**键；
`json_pointer` 与 store 写回仍用驼峰 `reportItem`（前端真源）。二者分离，参照 D4-8 的
`_CONTRACT_TO_STORE_FIELD` 教训（曾因直接用驼峰生成 180 个非法 key 打挂整份契约 parse）。

### 2.3 函数清单（与 D4-19 同名同签，仅后缀改 `_d44`）

`_snake` / `stable_key_for_d44` / `formula_mask_cells_d44` / `mapping_digest_payload_d44` /
`mapping_digest_d44` / `sheet_payload_d44` / `instrumentation_spec_d44` / `_decode` / `_rows` /
`build_store_projection_d44` / `merge_projection_into_d44_rows` / `store_item_id_d44`

`sheet_payload_d44()` 的 table 节：

```python
{
  "table_key": TABLE_KEY_D44,
  "anchor": f"A{FIRST_DATA_ROW_D44 - 1}",          # A5（表头行）
  "header_rows": 1,
  "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_KEY_D44}"},
  "delete_policy": "tombstone",
  "footer_anchor": {"marker": FOOTER_MARKER_D44, "search_column": "A",
                    "carries_total_formula": False},   # R21 是提示文本，非合计公式
  "formula_mask": [],
  "fields": [...],
}
```

`instrumentation_spec_d44()`：`table_name = f"GT_{TEMPLATE_ID_D44}_ROWS"`（= `GT_D44_ROWS`），
`managed_last_col="J"`, `uuid_col="K"`, `sheet_key="d44-managed"`。

## 3. 接线点（8 处，逐处核对）

🔴 这是本 spec 最易出错的部分。D4-8 曾只完成 5/8 处；13 个 item 曾因漏归一在
`oo_to_html.py:2842` 硬解包处 `ValueError` 打挂**整个 entry** 的回写。

| # | 文件 | 接线内容 |
|---|---|---|
| 1 | `phase5_d4_revenue_detail.py` | `from phase5_d4_adjustment_sheet import ...` + `_INCLUDE_D44_SHEET = True` |
| 2 | 同上 | `sheets` 列表加 `sheet_payload_d44()` |
| 3 | 同上 | `instrumentation_specs` 加 `instrumentation_spec_d44()` |
| 4 | 同上 | combined projection：`d44_projs` 默认值 **`[]` 不是 `{}`**（🔴 D4-8 踩过：非 list 时 `_decode` 返 None ⇒ 静默全投 0） |
| 5 | 同上 | `values.update(...)` 循环纳入 D4-4 |
| 6 | 同上 | `row_keys` 纳入 `{TABLE_KEY_D44: (...)}` |
| 7 | 同上 | `STORE_ITEM_IDS` 登记 `D4-4-rows`；`merge_projection_into_all_d4_stores` 末尾经 `_normalize_merge_updates` 归一 4-tuple |
| 8 | `oo_to_html.py` | D4-4 是 **list 形态**，走既有 rows 循环即可，**不**加进 `_dict_store_items`；须确认 `_mirror_d4_dual_stores` 能取到其 base |

> `STORE_ITEM_IDS` 与 `_normalize_merge_updates` 都定义在**生产者侧** `phase5_d4_revenue_detail.py`
> （现算：`oo_to_html.py` 里 `_normalize_merge_updates` 出现 0 次）。别去 `oo_to_html.py` 找它们。

## 4. 行身份两种格式并存（本表独有）

| 来源 | 格式 | 样例 |
|---|---|---|
| 前端 `generateRowId()` | `d4a-{base36时间}-{7位随机}` | `d4a-ms2p8tkl-juz5kck` |
| 导入侧 `_parse_d4_4_row` | 标准 `uuid4()` | `3f2a...-...` |

**设计决定**：`_rows()` 只校验「非空 + 不重复」，**不加格式正则**。UUID 载体列 K 写入原串。
理由：两种格式都是唯一字符串，引擎只需身份稳定；加格式校验会让导入产生的行在下次 sync 时被拒。
🔴 实施时**禁止**写 `assert rowId.startswith('d4a-')` 之类断言。

## 5. 前端改造

### 5.1 `D4TabAdjustment.vue`

```ts
import WorkpaperSyncEditorHost from '../../sync/WorkpaperSyncEditorHost.vue'
import { readStoreProjection } from '../../sync/workpaperSyncApi'
import { useD4SyncMode, D4_SYNC_ENTRY_ID } from '../composables/useD4SyncMode'

const { syncBridge, descriptor: syncOoDescriptor, editorMode, modeOptions, syncStateTag }
  = useD4SyncMode({
      sheetKey: 'd44-managed',
      // flushHtml: 先 flush 待存（debounce 2s 可能在途）再读 projection
      flushHtml: async () => {
        await flushPendingSave()
        const snap = await readStoreProjection({ projectId, wpId, entryId: D4_SYNC_ENTRY_ID })
        return { expectedRevision: snap.expectedRevision, projection: snap.projection,
                 sheetKey: 'd44-managed' }
      },
      ...
    })
```

模板：`<template v-if="editorMode==='在线编辑'"><div class="oo-container">
<WorkpaperSyncEditorHost v-if="syncOoDescriptor" :descriptor="syncOoDescriptor" :bridge="syncBridge" />`

🔴 `flushHtml` 必须先 `await flushPendingSave()`：`useD4Adjustment` 的 `debounceSave` 是 **2000ms**，
不 flush 就切 OO 会丢最后一次编辑。

### 5.1b 表格补 2 列（实测发现的三方不一致，Req 2.5 / 5.7）

2026-09-28 Playwright 实测：`D4TabAdjustment.vue` 的表格恰 8 个业务列，而模板有 10 列、
`D4AdjustmentRow` 类型有 10 个字段、`safeParseRows` 解析 10 个字段、导入导出（本批已补）也是 10 列
—— **只有 UI 少 2 列**。

```
现状 thead: 摘要 分类 报表项目 会计科目 附注项目 ──────── 借方 贷方 索引号 ────
目标 thead: 摘要 分类 报表项目 会计科目 附注项目 补充说明 借方 贷方 索引号 备注
                                            ↑ 新增 F                  ↑ 新增 J
```

照既有列范式补（`min-width` 参考「摘要」的 200 / 「报表项目」的 120）：

```vue
<!-- 6. 补充说明（模板 F 列「……」；字段 placeholder） -->
<el-table-column label="补充说明" min-width="140">
  <template #default="{ row }">
    <el-input v-if="!isReadonly" :model-value="row.placeholder" size="small"
              placeholder="补充说明"
              @change="(v: string) => updateCell(row.rowId, 'placeholder', v)" />
    <span v-else>{{ row.placeholder || '-' }}</span>
  </template>
</el-table-column>
```

⚠️ **同名陷阱**：上面 `el-input` 的 `placeholder="补充说明"` 是**占位文本属性**，
`row.placeholder` / `updateCell(..., 'placeholder', ...)` 才是 `D4AdjustmentRow` 的**字段**。
该文件里已有 6 处 `placeholder="…"` 占位属性（摘要/报表项目/会计科目/…），grep 时必须区分，
否则会误判「placeholder 字段已在 UI」。

**为何不能选「这 2 列不纳入受管」**：模板里 F/J 列真实存在 ⇒ OO 侧用户可以编辑它们 ⇒ 若不纳入受管，
materialize 会拿 store 旧值覆盖用户在 OO 的输入（静默丢数据）。纳入受管但 UI 不显示同样坏
（改动存进 store 却在结构化视图看不见，表现为「改动丢了」，比不回写更难排查）。故唯一正确解是
**五层一致**：模板 / 类型 / 解析 / UI / 导入导出 都是 10 列。

### 5.2 宿主与禁入名单（两处必须同批改）

| 文件 | 改动 |
|---|---|
| `GtD4OperatingRevenue.vue` | `isD4DedicatedSyncSheet` 数组加 `'D4-4'` |
| `composables/d4Constants.ts` | `D4_LEGACY_OO_BLOCKED_SHEETS` 移除 `'D4-4'`（保留 `'D4-5'`） |

🔴 只改其一都会坏：只加 dedicated 不摘名单 ⇒ `isLegacyOoBlocked` 使 `renderMode` 恒 `'html'`、
切换器恒 disabled，新桥点不进；只摘名单不加 dedicated ⇒ 掉回 legacy `GtOnlyOfficeSheet` 单向通道
（退回修复前的静默丢失）。

`d4LegacyOoBlocked.spec.ts` 需同步更新三处用例：`isD4LegacyOoBlocked('D4-4')` 期望翻 `false`、
「dedicated 表不进名单」的交集期望、「推导 legacy 命中集」从 4 张变 5 张（D4-4 归入 dedicated 后
不再出现在 legacy 集，但该用例是按「不在两个桥且不在名单」推导的 —— 须重算期望值）。

## 6. 测试策略

| 层 | 文件 | 内容 |
|---|---|---|
| 契约/几何 | `backend/tests/test_d4_4_adjustment_contract.py`（新） | 几何常量 vs openpyxl 实测逐项对账；字段 10 个；`formula_mask` 空；`stable_field_key` 全小写；`parse_contract(build_contract_payload())` 不抛 |
| 往返 | 同上 | `build_store_projection_d44` → `merge_projection_into_d44_rows` 等值；两种 rowId 格式各跑一遍；空 payload / 裸 list 容差（D4-9 曾因 bare list 抛 `StorePayloadError` 卡死全 entry rematerialize） |
| 消费侧 | `test_d4_mirror_shape_invariants.py`（扩） | D4-4 的 merge 返回是 4-tuple；store item ∈ `STORE_ITEM_IDS`；**变异反证**：monkeypatch 掉归一 → 复现 ValueError |
| 前端接线 | `d4AdjustmentSyncHostWiring.spec.ts`（新） | 组件经 `useD4SyncMode` 接桥 + 挂 `WorkpaperSyncEditorHost` + `.oo-container` 存在 + sheetKey 字面量 `d44-managed` |
| 前端名单 | `d4LegacyOoBlocked.spec.ts`（改） | D4-4 已摘出、D4-5 仍在、命中集期望重算 |
| 既有回归 | `test_d4_4_import_export_roundtrip.py`（12）不得转红 | 导入导出 10 列往返 |
| E2E L1 | `e2e/d4-bidirectional-acceptance.spec.ts` | D4-4 加入 `D4_ACCEPT_SHEETS`；`--workers=1` |

**变异反证清单**（每条都要实做，不是写完就算）：
1. 字段表删 `placeholder` → 契约字段数断言红
2. `UUID_COL_D44` 改成 `J`（撞受管列）→ 几何对账红
3. 去掉 `_normalize_merge_updates` 归一 → mirror 不变量红 + ValueError 复现
4. `d4Constants.ts` 名单里留着 `'D4-4'` → 前端名单用例红

## 7. 发布链（需 live PG）

```
python backend/scripts/gen/generate_phase5_d4_contract.py --apply      # 契约 35 → 36 张
python backend/scripts/fix/fix_task76_provision_projection_definitions.py   # provision
python backend/scripts/diagnose/d43_rematerialize_dual_sheet.py --apply     # 发布 representation
python backend/scripts/diagnose/d43_rematerialize_dual_sheet.py --check     # 期望 already_on_desired_bundle
```

时间预算：Wave 5 后基线 69.33s，D4-33 后 82.53s。D4-4 仅 10 字段 / 15 行，增量极小，
预计仍远低于 120s soft_limit。若意外超时，按 `workpaper-sync-materialize-large-table-performance`
design §11.4 的 P1（adapter.extract 多 binding 解析共享）处理，**不得提高 soft_limit**。

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 行数 > 15 时插行越过 R21 提示文本 | footer marker `提示：` 给出下界，引擎在 marker 前插行；测试造 20 行验证提示文本仍在且未被覆盖 |
| 两种 rowId 格式导致校验拒收 | `_rows()` 不加格式校验（§4）；测试两种格式各跑一遍 |
| 摘名单/加 dedicated 只做一半 | 两处改动写进同一 task，且 `d4LegacyOoBlocked.spec.ts` + `d4AdjustmentSyncHostWiring.spec.ts` 双向钉死 |
| `d44_projs` 默认值写成 `{}` | 契约测试加「空 base 不投 0」守卫（D4-8 同型） |
| debounce 2s 在途数据丢失 | `flushHtml` 先 `await flushPendingSave()` |
| L2 因空白行落进 empty_payload_skip | 先 seed 带借贷金额的业务行（Req 7.3） |
| 契约 schema 校验器拒收诚实声明 | 若遇 N 轮 NC-33 同型问题（越如实点名越通不过），走追加节绕开并登记，不改判据去迎合校验器 |

## 9. 不做什么

- **不建独立 entry**：沿用共享 `xlsx/gt-d4-operating-revenue`（D4-9 曾拟独立 entry 后并入共享，
  其 `d4.customer_structure.json` 已废弃 —— 不重犯）。
- **不动公式管理**：D4-4 的借贷合计/平衡差额是审计硬规则，不应让用户改公式。若将来要给 D4-4 加
  `open-formula-manager` 入口，属另一件事（且需注意现有 4 个 D4 入口只传 `nodeKey` 不传 `wpId`，
  会使 `formulaContext` 为 undefined —— 该平台级同型问题不在本 spec 范围）。
- **不修 pre-existing 红** `test_d4_price_import_formula_preserve.py::test_parse_d4_9_and_d4_11_field_mapping`
  （owner = D4-9，已实证与本批无关）。
- **不回填归档 spec**：`_archive/.../d4-adjustment-and-analysis-gap-closure` 保持原样。
